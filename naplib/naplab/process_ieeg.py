import logging
import warnings
import os
from typing import Union, Tuple, List, Optional, Dict, Sequence, Callable
from tqdm.auto import tqdm

import numpy as np
from scipy.signal import resample, welch, correlate
from scipy.interpolate import interp1d
from scipy.spatial.distance import pdist, squareform
from scipy.stats import pearsonr

import matplotlib.pyplot as plt

from hdf5storage import loadmat

from naplib.io import load_tdt, load_nwb, load_edf, load, load_wav_dir
from naplib import preprocessing
from naplib.features import auditory_spectrogram
from naplib import Data as nlData
from .alignment import align_stimulus_to_recording

ACCEPTED_DATA_TYPES = ['edf', 'tdt', 'nwb', 'pkl']
LOG_LEVELS = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO, 'WARNING': logging.WARNING, 'ERROR': logging.ERROR, 'CRITICAL': logging.CRITICAL}
BUFFER_TIME = 2 # seconds of buffer in addition to befaft so that filtering doesn't produce edge effects


def process_ieeg(
    data_path: str,
    alignment_dir: str,
    stim_order_path: Optional[str]=None,
    stim_dirs: Optional[Dict[str, str]]=None,
    data_type: str='infer',
    rereference_grid: Optional[np.ndarray]=None,
    rereference_method: str='avg',
    store_reference: bool=False,
    aud_channel: Union[str, int]='infer',
    aud_channel_infer_method: str='crosscorr',
    bands: Union[str, List[str], List[np.ndarray], List[float], np.ndarray]=['highgamma'],
    phase_amp: str='amp',
    befaft: Union[List, np.ndarray]=[1, 1],
    intermediate_fs: Optional[int]=600,
    final_fs: int=100,
    alignment_kwargs: dict={},
    line_noise_kwargs: dict={},
    store_sounds: bool=False,
    store_all_wav: bool=False,
    aud_fn: Optional[Union[str, Callable]]='default',
    aud_kwargs: dict={},
    n_jobs: int=1,
    log_level : str='INFO'
):
    """
    data_path : str path-like
        String specifying data directory (for TDT) or file path for raw data file
    alignment_dir : str path-like
        Directory containing a set of stimulus waveforms as .wav files for alignment. This will be called 'aud'.
    stim_order_path : Optional[str] path-like, defaults to ``alignment_dir``
        If a file, must be either a StimOrder.mat file, or StimOrder.txt file containing the order of the
        stimuli names as lines in the file, which should correspond to the names of the .wav files in ``alignment_dir``. If a
        directory, the directory must contain such a file. If None, will search for such a file within
        ``alignment_dir``.
    stim_dirs : Optional[Dict[str, str]], defaults to ``alignment_dir``
        If not provided, alignment_dir is assumed to contain the stimulus as well.
        If provided, can be used to specify additional paths from which to load sounds which will be converted to the
        chosen spectrotemporal features. This dict should have keys which are the name for the stimuli and values
        which are the path to the stimulus directory of wav files. The files within this must have the same names
        as those within ``stim_dir``. E.g. {'aud': './stimuli', 'aud_spk1': './stimuli_spk1', 'aud_spk2': './stimuli_spk2'}
    data_type : str, default='infer'
        One of {'edf', 'tdt', 'nwb', 'pkl', 'infer'}. The data type of the raw neural data to load.
    rereference_grid : Optional[np.ndarray], default=None
        If not None, then data are re-referenced based on this referencing scheme. If a numpy array, then
        should specify categorical groupings of which electrodes to be grouped together for re-referencing,
        and must be the same length as the number of electrodes in the raw data.
    rereference_method : Optional[str], default='avg'
        If provided, must specify a method for common rereferencing, either 'avg' (average), 'pca' (PCA),
        or 'med' (median). Only used if ``rereference_grid`` is not None.
    store_reference : bool, default=False
        If True, include the reference which was subtracted from each channel in the output Data.
    aud_channel : Union[str, int], default='infer',
        If an int, specifies the index of the wav channel loaded from the raw recording which
        should be used for alignment. If 'infer', then this is inferred.
    aud_channel_infer_method : str, default='crosscorr'
        Method for inferring aud channel used for alignment, either 'crosscorr','spectrum', or 'interactive'.
        'crosscorr' computes cross correlation between stimulus waveform and each wav channel and selects
        maximum. 'spectrum' compares the power spectra of each wav channel to that of the stimulus and chooses
        the maximum (which is not very robust when using certain alignment stimuli like triggers).
        'interactive' prints the name of each wav channel and asks the user to specify which one
        should be used for alignment. This is only an option when wav_labels are present, which is
        only for some data types (like edf).
    bands : Union[str, list[str], list[np.ndarray], list[float], np.ndarray], default=['highgamma']
        Frequency bands, specified as either strings or array-likes of length 2 giving the lower
        and upper bounds. For example, [[8, 13], np.array([30, 70]), 'highgamma'] is equivalent
        to ['theta', 'gamma', [30, 70]]. Or, can use 'raw' to specify raw neural data. Keep in mind,
        this will still be resampled according to the ``final_fs`` parameter.
    phase_amp : str, default='amp'
        Whether to save the phase, amplitude, or both, of each extracted frequency band. Options
        are {'phase', 'amp', 'both'}.
    befaft : Union[List, np.ndarray], default=[1,1]
        Extra time (in sec.) to store from the neural data before the start of and after the end of each
        stimulus.
    intermediate_fs : Optional[int], default=600
        If provided downsamples the loaded raw neural data to this sampling rate before further
        preprocessing. If this is greater than the raw sampling rate, no resampling is done.
    final_fs : int, default=100
        Final sampling rate for neural data and spectrograms.
    alignment_kwargs : dict, default={}
        If provided, will be passed to naplib.naplab.align_stimulus_to_recording to override keyword arguments.
    line_noise_kwargs : dict, default={}
        Dict of kwargs to naplib.preprocessing.filter_line_noise
    store_sounds : bool, default=False
        If True, store raw sound wave for each stimulus in stim_dirs in the output Data.
    store_all_wav : bool, default=False
        If True, store all recorded wav channels that were stored by the neural recording hardware. This may include
        any other signals that were hooked up at the same time, such as EKG, triggers, etc.
    aud_fn : Optional[Union[str, Callable]], default='default'
        Function for computing spectrogram from trial stimulus sounds. If None or 'none', no spectrograms will be
        computed. If 'default', ``naplib.features.auditory_spectrogram`` will be used. If a callable ``f``, the
        function will be applied to each stimulus audio and should have signature
        ``(x: NDArray, sr: float, **aud_kwargs) -> NDArray``, where ``x`` is 1-D audio signal with shape
        (in_samples,) and ``sr`` is the sampling rate of the audio. The returned array (spectrogram) should
        have shape (n_samples, freq_bins).
    aud_kwargs : dict, default={}
        Keyword arguments to pass to ``aud_fn``. In case of the default function ``naplib.features.auditory_spectrogram``,
        it can include overrides for frame_len, tc, and factor.
    n_jobs : int, default=1
        Number of CPU cores to use for the parallelizable processes. Higher number of jobs also uses higher memory,
        so there might even be a negative effect when working with large datasets.
    log_level : str, default='INFO'
        In order of the amount that will be displayed from most to least, can be
        one of {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        
    Returns
    -------
    data : nl.Data
        Data object containing all requested fields after preprocessing.
    """

    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVELS[log_level.upper()])
    handler = logging.FileHandler('Img_To_Local_Python.log', 'w', 'utf-8')
    root_logger.addHandler(handler)

    # # infer spectrogram function
    if aud_fn == 'default':
        aud_fn = auditory_spectrogram
    elif aud_fn == 'none':
        aud_fn = None
    elif not isinstance(aud_fn, Callable):
        raise ValueError("Argument aud_fn should be either 'none', 'default', or a function")

    # # infer data type
    if data_type is None or data_type not in ACCEPTED_DATA_TYPES:
        data_type, data_path = _infer_data_type(data_path)
        logging.info(f'Inferred data type to be {data_type} from the data directory')
    
    if len(befaft) != 2:
        raise ValueError(f'befaft must be a list or array of length 2.')
    
    # # load data and aud channels
    if data_type == 'tdt':
        logging.info(f'Loading tdt data...')
        raw_data = load_tdt(data_path)
        
    elif data_type == 'nwb':
        logging.info(f'Loading nwb data...')
        if not data_path.endswith(('.nwb', '.NWB')):
            raise ValueError(f'data_type is nwb but data_path is not a nwb file: {data_path}')
        raw_data = load_nwb(data_path)

    elif data_type == 'edf':
        logging.info(f'Loading edf data...')
        if not data_path.endswith(('.edf', '.EDF')):
            raise ValueError(f'data_type is edf but data_path is not an edf file: {data_path}')
        raw_data = load_edf(data_path)
        
    elif data_type == 'pkl':
        if not data_path.endswith(('.pkl', '.p')):
            raise ValueError(f'data_type is pkl but data_path is not a pkl file: {data_path}')
        logging.info(f'Loading pkl data...')
        raw_data = load(data_path)
        if not isinstance(raw_data, dict) or ('data' not in raw_data or 'data_f' not in raw_data or 'wav' not in raw_data or 'wav_f' not in raw_data):
            raise ValueError(f'pkl data is not formatted correctly. Must be a pickled dict containing "data", "data_f", "wav", "wav_f" keys at least')
        if store_all_wav and 'labels_wav' not in raw_data:
            raise ValueError('store_all_wav is True, but to store wav channels in final output there must be the key "labels_wav" in the pickled data.')
    else:
        raise ValueError(f'Invalid data_type parameter. Must be one of {ACCEPTED_DATA_TYPES}')

    # # load StimOrder
    logging.info('Loading StimOrder...')
    if stim_order_path is not None:
        stim_order = _load_stim_order(stim_order_path)
    else:
        stim_order = _load_stim_order(alignment_dir)

    data_f = raw_data['data_f']
    
    # # resample to intermediate_fs Hz
    if intermediate_fs is not None and data_f > intermediate_fs and intermediate_fs >= final_fs:
        new_len = int(intermediate_fs / float(data_f) * raw_data['data'].shape[0])
        logging.info(f'Resampling data to {intermediate_fs} Hz')
        raw_data['data'] = resample(raw_data['data'], new_len, axis=0)
        data_f = intermediate_fs
        raw_data['data_f'] = intermediate_fs

    # # load stimuli files
    logging.info('Loading stimuli...')
    stim_data = load_wav_dir(alignment_dir, rescale=True, subset=set(stim_order))
    if stim_dirs is not None:
        extra_stim_data = {k: load_wav_dir(stim_dir2, rescale=True, subset=set(stim_order)) for k, stim_dir2 in stim_dirs.items()}

    else:
        extra_stim_data = {'aud': stim_data}

    # # figure out which channel is used for alignment
    if aud_channel == 'infer':
        logging.info(f'Inferring alignment channel from wav channels...')
        alignment_wav, alignment_ch = _infer_aud_channel(raw_data['wav'],
                                                         raw_data['wav_f'],
                                                         raw_data.get('wav_labels', None),
                                                         list(stim_data.values()),
                                                         method=aud_channel_infer_method,
                                                         debug=log_level.upper()=='DEBUG')
        logging.info(f'Inferred alignment channel is {alignment_ch}.')
    else:
        if raw_data['wav'].ndim > 1:
            if not isinstance(aud_channel, int):
                raise TypeError(f'Invalid aud_channel argument. Must either be "infer" or an int specifying'
                                f' an index of the raw audio channels to use, but got {aud_channel}')
            alignment_wav = raw_data['wav'][:,aud_channel]
            alignment_ch = aud_channel
        else:
            alignment_wav = raw_data['wav']
            alignment_ch = aud_channel
    
    # # perform alignment
    alignment_times, alignment_confidence = align_stimulus_to_recording(
        alignment_wav, raw_data['wav_f'], stim_data, stim_order, verbose=_verbosity(log_level), **alignment_kwargs
    )
    
    # truncate data around earliest and lastest time that we need
    earliest_time = max([alignment_times[0][0] - BUFFER_TIME-1, 0])
    latest_time = alignment_times[-1][1] + BUFFER_TIME+1
    if befaft[0] > alignment_times[0][0]:
        raise ValueError(f"Not enough data to use befaft[0]={befaft[0]}. First stimulus aligned to {alignment_times[0][0]} sec")

    if befaft[1] > raw_data['data'].shape[0] / data_f - alignment_times[-1][1]:
        raise ValueError(f"Not enough data to use befaft[1]={befaft[1]}. Last stimulus alignment ends at {alignment_times[-1][1]} sec but"
                         f" only have {raw_data['data'].shape[0] / data_f} sec of data")
    
    alignment_times = np.asarray(alignment_times) - earliest_time # shift times back since we are going to truncate the data
    earliest_sample = int(raw_data['data_f'] * earliest_time)
    latest_sample = int(raw_data['data_f'] * latest_time)
    raw_data['data'] = raw_data['data'][earliest_sample:latest_sample].copy()
    raw_data['wav'] = raw_data['wav'][earliest_sample:latest_sample].copy()

    # # append befaft zeros to the stims which were not used for alignment as well as the one which was (if it's in the dict too)
    for stim_data_name, stim_data_dict_ in extra_stim_data.items():
        for wavname_, wavdata_ in stim_data_dict_.items():
            bef_zeros = int(round(wavdata_[0] * befaft[0]))
            aft_zeros = int(round(wavdata_[0] * befaft[1]))
            if wavdata_[1].ndim == 1:
                stim_data_dict_[wavname_] = wavdata_[0], np.pad(wavdata_[1], (bef_zeros,aft_zeros))
            else:
                stim_data_dict_[wavname_] = wavdata_[0], np.pad(wavdata_[1], ((bef_zeros,aft_zeros), (0,0)))

    
    # # preprocessing
    
    # # common referencing
    if rereference_grid is not None:
        logging.info(f'Performing commong rereferencing using "{rereference_method}" method...')
        if store_reference:
            rereferenced_data, reference_to_store = preprocessing.rereference(rereference_grid, field=[raw_data['data']], method=rereference_method, return_reference=True)
        else:
            rereferenced_data = preprocessing.rereference(rereference_grid, field=[raw_data['data']], method=rereference_method, return_reference=False)
            reference_to_store = None
        raw_data['data'] = rereferenced_data[0]
    else:
        reference_to_store = None
    
    # filter line noise (after this, raw_data['data'] is a list of length 1)
    logging.info('Filtering line noise...')
    raw_data['data'] = preprocessing.filter_line_noise(field=[raw_data['data']],
                                                       fs=raw_data['data_f'],
                                                       in_place=True,
                                                       verbose=_verbosity(log_level),
                                                       **line_noise_kwargs)

        
    # # Cut raw data up into blocks based on alignment
    logging.info('Chunking responses based on alignment...')
    data_by_trials_raw = _split_data_on_alignment(nlData({'raw': raw_data['data']}), raw_data['data_f'], alignment_times, befaft, buffer_time=BUFFER_TIME)

    # print('split by trials')
    # print(data_by_trials_raw['raw'][0].shape)

    # # extract frequency bands
    if 'raw' in bands:
        include_raw = True
        bands = [bb for bb in bands if bb != 'raw']
    else:
        include_raw = False
    Wn = _infer_freq_bands(bands) # get frequency bands from string names
    bandnames = []
    for band, wn_ in zip(bands, Wn):
        if isinstance(band, str):
            bandnames.append(band)
        else:
            bandnames.append(str(wn_))
    

    if len(Wn) > 0:
        logging.info(f'Extracting frequency bands: {Wn} ...')
        data_by_trials = preprocessing.phase_amplitude_extract(field=data_by_trials_raw['raw'],
                                                               fs=raw_data['data_f'],
                                                               Wn=Wn, bandnames=bandnames,
                                                               fs_out=final_fs,
                                                               n_jobs=n_jobs,
                                                               verbose=_verbosity(log_level))

        logging.info(f'Storing response bands of interest...')
        # only keep amplitude or phase if that's what the user specified
        if phase_amp == 'amp':
            fields_to_keep = [xx for xx in data_by_trials.fields if ' amp' in xx]
        elif phase_amp == 'phase':
            fields_to_keep = [xx for xx in data_by_trials.fields if ' phase' in xx]
        else:
            fields_to_keep = data_by_trials.fields
        data_by_trials = data_by_trials[fields_to_keep]

        if include_raw:
            data_by_trials['raw'] = data_by_trials_raw['raw']

    else:
        # if no other frequency bands, then default to output raw
        data_by_trials = data_by_trials_raw

    desired_lens = [round(final_fs / raw_data['data_f'] * len(xx)) for xx in data_by_trials_raw['raw']]


    if 'raw' in data_by_trials.fields:
        data_by_trials['raw'] = [resample(xx, d_len, axis=0) for xx, d_len in zip(data_by_trials_raw['raw'], desired_lens)]

    if reference_to_store is not None:
        reference_to_store = _split_data_on_alignment(nlData({'ref': reference_to_store}), raw_data['data_f'], alignment_times, befaft, buffer_time=BUFFER_TIME)
        data_by_trials['reference'] = [resample(xx, d_len, axis=0) for xx, d_len in zip(reference_to_store['ref'], desired_lens)]
    
    data_by_trials = _remove_buffer_time(data_by_trials, final_fs, buffer_time=BUFFER_TIME)

    if store_all_wav:
        logging.info('Chunking wav channels based on alignment...')
        wav_data_chunks = _split_data_on_alignment(nlData({'wav': [raw_data['wav']]}), raw_data['wav_f'], alignment_times, befaft, buffer_time=0)

    # final output dict to be made into naplib.Data object
    alignment_times = np.asarray(alignment_times)
    final_output = {'name': stim_order,
                    'alignment_start': list(alignment_times[:,0] + earliest_time),
                    'alignment_end': list(alignment_times[:,1] + earliest_time),
                    'alignment_confidence': alignment_confidence,
                    'dataf': [final_fs for _ in stim_order],
                    'befaft': [befaft for _ in stim_order]}

    # extract spectrograms
    if aud_fn:
        logging.info(f'Computing auditory spectrogram for each stimulus set in stim_dirs ...')
        # mapping from name (like 'aud') to list of spectrograms
        for k, stim_data_dict in extra_stim_data.items():
            final_output[k] = _spectrograms_from_stims(stim_data_dict, stim_order, final_fs, aud_fn, aud_kwargs, verbose=_verbosity(log_level) >= 1)
    
    if store_sounds:
        for k, stim_data_dict in extra_stim_data.items():
            final_output[f'{k} sound'] = [stim_data_dict[stim_name][1] for stim_name in stim_order]
            final_output[f'{k} soundf'] = [stim_data_dict[stim_name][0] for stim_name in stim_order]

    del extra_stim_data
    
    final_output['data_type'] = [data_type for _ in stim_order]
    
    for fieldname in data_by_trials.fields:
        final_output[fieldname] = data_by_trials[fieldname]
        
    if store_all_wav:
        final_output['wavf'] = [raw_data['wav_f'] for _ in stim_order]
        for ww, wav_ch_name in enumerate(raw_data['labels_wav']):
            final_output[wav_ch_name] = [xx[:,ww] for xx in wav_data_chunks['wav']]
    
    # # Put output Data all together
    final_output = nlData(final_output)
    final_output.set_info({'channel_labels': raw_data.get('labels_data', None),
                           'rereference_grid': rereference_grid})
    logging.info('All done!')
    return final_output
    

    # # electrode localization
    # elec_locs
        
    
def _infer_aud_channel(wav_data: np.ndarray, wav_fs: int, wav_labels: Sequence[str],
                       stim_data: List[Tuple[float, np.ndarray]],
                       method: str='crosscorr', min_freq=20, debug=False):
    """
    Infer which recorded wav channel matches the stimulus waveforms provided.
    
    Parameters
    ----------
    wav_data : np.ndarray, shape (time, channels)
        Loaded wav channels from the recording system. Should be of shape (time, channels)
    wav_fs : int
        Sampling rate of wav data.
    wav_labels : Sequence[str]
        Name for each wav channel.
    stim_data : List[Tuple[float, np.ndarray]]
        List of tuples containing sampling rate and stimuli sounds/trigger waveforms,
        each of shape (time, ) or (time, 2). If stereo, the left channel will be used.
    method : str, default='spectrum'
        Method for inferring correct channel from wav_data. Options are 'spectrum', 'envelope',
        'crosscorr', or 'interactive'.
        'crosscorr' computes cross correlation between stimulus waveform and each wav channel and selects
        maximum. 'spectrum' compares the power spectra of each wav channel to that of the stimulus and chooses
        the maximum (which is not very robust when using certain alignment stimuli like triggers).
        'interactive' plots each wav channel and asks the user to specify which one should be used for alignment.
    min_freq : float, default=20
        Only used if method='spectrum'. Minimum frequency to include when calculating correlation
        between spectrums.
    debug : bool, default=False
        If True, plots the spectrum of each channel and the spectrum of the stimulus.

    Returns
    -------
    alignment_wav : np.ndarray
        The channel from wav_data which matches the stimuli given. Will have shape (time, )
    alignment_index : int
        Index from wav_data channels which was picked as the alignment channel
        
    """
    if wav_data.ndim == 1:
        return wav_data, wav_fs
    if wav_data.shape[1] == 1:
        return wav_data[:,0], wav_fs
    
    assert isinstance(stim_data, list)

    if method == 'interactive':
        if wav_labels is None:
            raise ValueError('Interactive mode only supported when wav_labels is available.')

        print(f'These are the available channels: {", ".join(wav_labels)}.')
        ch_idx = None
        while ch_idx is None:
            pick = input('Which is the audio channel? ').strip()
            for i, s in enumerate(wav_labels):
                if pick == s:
                    ch_idx = i
                    break

        return wav_data[:, ch_idx], ch_idx

    elif method == 'spectrum':
        fs0 = stim_data[0][0]
        concat_stims = []
        for i, (fs, stim_waveform) in enumerate(stim_data):
            if fs != fs0:
                raise ValueError(f'Sampling rates are not all the same. First stimulus has sampling rate of'
                                 f' {fs0} Hz, and stimulus {i} has sampling rate of {fs}')
            concat_stims.append(stim_waveform)

        concat_stims = np.concatenate(concat_stims, axis=0)
        # select left channel of stimuli only
        if concat_stims.ndim > 1:
            concat_stims = concat_stims[:,0][:,np.newaxis]
            
        # compute spectrum of wav data and stimuli
        f1, px1 = welch(wav_data, fs=wav_fs, axis=0)
        f2, px2 = welch(concat_stims, fs=fs0, axis=0)


        if wav_fs > fs0:
            # downsample px1 and move to range of f2
            new_px1 = []
            for ii in range(px1.shape[1]): 
                interp = interp1d(f1, px1[:,ii])
                new_px1.append(interp(f2))
            px1 = np.vstack(new_px1).T # back to shape (freqs, channels)
            shared_f = f1
        elif fs0 > wav_fs:
            # downsample px2 and move to range of f1
            interp = interp1d(f2, px2.squeeze())
            px2 = interp(f1)[:,np.newaxis]
            shared_f = f1
        else:
            shared_f = f1


        good_freqs = shared_f >= min_freq
        shared_f = shared_f[good_freqs]
        px1 = px1[good_freqs]
        px2 = px2[good_freqs]

        if px2.ndim == 1:
            px2 = px2[:,np.newaxis]

        cat_px = np.concatenate([px1, px2], axis=1)
        dists = 1.0-pdist(cat_px.T, metric='correlation')
        dists = squareform(dists)
        best_ch_idx = np.nanargmax(dists[:,-1])
        
        if debug:
            plt.figure(figsize=(8,6))
            plt.title('Spectrums of Stimulus and Wav Channels')
            plt.plot(shared_f, px2/px2.max(), color='k', label='Stimulus')
            for jj in range(px1.shape[1]):
                plt.plot(shared_f, px1[:,jj]/px1[:,jj].max(), label='Ch {}: crr={:.3f}'.format(jj, dists[jj,-1]))
            plt.legend()
            plt.show()
        
        return wav_data[:, best_ch_idx], best_ch_idx
    
    elif method == 'crosscorr' or method == 'xcorr':
        # Find longest stimulus for more robust inference
        longest_stim = np.argmax(len(s)/f for f, s in stim_data)
        stim_fs, stim_data = stim_data[longest_stim]

        desired_len = int(wav_fs / stim_fs * len(stim_data))
        if desired_len != len(stim_data):
            stim_data = resample(stim_data, desired_len, axis=0)

        if stim_data.ndim > 1 and stim_data.shape[1] > 1:
            logging.warning('Performing alignment with stereo audio stimuli is not recommended.'
                            ' It is recommended to use mono-channel audio for alignment, and any'
                            ' additional stimuli (including stereo audio) desired in the final '
                            ' Data object can be specified as extra stimulus directories.')

        scores = []
        for c in range(wav_data.shape[1]):
            if stim_data.ndim == 1 or stim_data.shape[1] == 1:
                pos = np.nanargmax(correlate(wav_data[:, c], stim_data.squeeze(), 'valid'))
                score = pearsonr(wav_data[pos:pos+len(stim_data), c], stim_data.squeeze())[0]
            else:
                pos_left = np.nanargmax(correlate(wav_data[:, c], stim_data[:,0], 'valid'))
                score_left = pearsonr(wav_data[pos_left:pos_left+len(stim_data), c], stim_data[:,0])[0]
                pos_right = np.nanargmax(correlate(wav_data[:, c], stim_data[:,1], 'valid'))
                score_right = pearsonr(wav_data[pos_right:pos_right+len(stim_data), c], stim_data[:,1])[0]
                score = np.nanmax([score_left, score_right])
            scores.append(score)

        if debug:
            logging.info(f'Alignment xcorr scores: {", ".join(str(s) for s in scores)}')

        best_ch_idx = np.nanargmax(scores)

        return wav_data[:,best_ch_idx], best_ch_idx
    
    else:
        raise ValueError(f'Unsupported method argument: {method}')
        
            
    
def _infer_freq_bands(
    bands: Union[str, List[str], List[np.ndarray], List[float], np.ndarray]
) -> List[List[Union[float, int]]]:
    """
    Parameters
    ----------
    bands : Union[str, List[str], List[np.ndarray], List[float], np.ndarray]
        Bands to translate into lower and upper frequency ranges. Allowed strings
        are 'theta', 'alpha', 'gamma', 'highgamma'.
        
    Returns
    -------
    band_bounds : List[List[Union[float, int]]]
        List of bands, each band specified as a list of length 2 containing the lower
        and upper bound of the frequency band.
    """
    
    FREQUENCY_BANDS = {'theta': [4,8], 'alpha': [8, 13],
                       'gamma': [30, 70], 'highgamma': [70, 150]}
    
    new_bands = []
    if isinstance(bands, list):
        if len(bands) == 2 and all([isinstance(x, float) or isinstance(x, int) for x in bands]):
            # just a list of length 2, so these are lower and upper bounds
            new_bands.append(bands)
        else:
            for band in bands:
                if isinstance(band, str):
                    if band not in FREQUENCY_BANDS:
                        raise ValueError(f'Invalid band name. If a string, must be one of {FREQUENCY_BANDS}, but got {band}')
                    else:
                        new_bands.append(FREQUENCY_BANDS[band])
                else:
                    if (not isinstance(band, np.ndarray) and not isinstance(band, list)) or len(band) != 2:
                        raise ValueError(f'each band must be a list of numpy array of length 2, but found band {band}')
                    new_bands.append(list(band))
                    
    elif isinstance(bands, str):
        new_bands.append(FREQUENCY_BANDS[bands])
    
    else:
        if not isinstance(bands, np.ndarray):
            raise TypeError('bands is neither a string, nor a list, nor a numpy array.')
        elif bands.squeeze().shape != (2,):
            raise ValueError(f'bands must only have two elements if given as numpy array but got bands of shape {bands.shape}')
        else:
            new_bands.append(list(bands))
    
    return new_bands
    
def _infer_data_type(data_path: str):
    """
    Infer which data loader to use based on what files are in the directory or the file extension
    if a single file is given.
    
    Parameters
    ----------
    data_path : str, path-like
        Directory or file containing data
    
    Returns
    -------
    data_type : str
        One of 'tdt', 'edf', 'nwb', 'pkl'.
    file_path : str
        Path to file or directory which contains the data.
    """
    if data_path.endswith(('.edf', '.EDF')):
        return 'edf', data_path
        
    if data_path.endswith(('.nwb', '.NWB')):
        return 'nwb', data_path
    
    if data_path.endswith(('.pkl', '.p')):
        return 'pkl', data_path
    
    files_in_dir = [x for x in os.listdir(data_path) if '.' in x and x[0]!='.']
    file_suffixes = [x.split('.')[-1] for x in files_in_dir]
    
    if 'sev' in file_suffixes or 'tev' in file_suffixes:
        if 'tev' in file_suffixes:
            return 'tdt', data_path
        else:
            raise ValueError('sev file(s) found in directory but no tev file found.')
    elif 'edf' in file_suffixes or 'EDF' in file_suffixes:
        if file_suffixes.count('edf') + file_suffixes.count('EDF') > 1:
            raise ValueError(f'Inferred edf format, but more than one edf file found in given directory.')
        if 'edf' in file_suffixes:
            return 'edf', os.path.join(data_path, files_in_dir[file_suffixes.index('edf')])
        else:
            return 'edf', os.path.join(data_path, files_in_dir[file_suffixes.index('EDF')])
    elif 'nwb' in file_suffixes or 'NWB' in file_suffixes:
        if file_suffixes.count('nwb') + file_suffixes.count('NWB') > 1:
            raise ValueError(f'Inferred nwb format, but more than one nwb file found in given directory.')
        if 'nwb' in file_suffixes:
            return 'nwb', os.path.join(data_path, files_in_dir[file_suffixes.index('nwb')])
        else:
            return 'nwb', os.path.join(data_path, files_in_dir[file_suffixes.index('NWB')])
    elif 'pkl' in file_suffixes or 'p' in file_suffixes:
        if file_suffixes.count('pkl') + file_suffixes.count('p') > 1:
            raise ValueError(f'Inferred pkl format, but more than one pickle file found in given directory.')
        if 'pkl' in file_suffixes:
            return 'pkl', os.path.join(data_path, files_in_dir[file_suffixes.index('pkl')])
        else:
            return 'pkl', os.path.join(data_path, files_in_dir[file_suffixes.index('p')])
    
    raise ValueError(f'Could not infer data type from directory.')


def _spectrograms_from_stims(stim_data_dict, stim_order, fs_out, aud_fn, aud_kwargs={}, verbose=False):
    """
    Convert each stimulus in the stim_data_dict into a spectrogram, then return
    a list of spectrograms ordered by stim_order (stimuli can repeat in stim_order).
    
    Parameters
    ----------
    stim_data_dict : dict
        Dictionary mapping from string name of stimulus to a tuple of (fs, wav_data)
    stim_order : list of strings
        List of names in desired order. Each name must be a key that exists in stims_data_dict,
        but they can repeat.
    fs_out : int
        Sampling rate of output spectrograms
    aud_fn : Callable
        Function for computing spectrogram from waveform. The function should have signature
        ``(x: NDArray, sr: float, **kwargs) -> NDArray`` where x has shape (in_samples,), sr
        is the sampling rate of x, and the return value has shape (out_samples, freq_bins).
    aud_kwargs : dict, default={}
        Dictionary of kwargs for ``aud_fn``
    
    Returns
    -------
    specs : list of np.ndarray
        List of same length as stim_order containing the spectrogram for each stimulus
    """
    spec_dict = {}
    stim_data_dict = stim_data_dict.items()
    for k, (fs, sig) in tqdm(stim_data_dict, total=len(stim_data_dict)) if verbose else stim_data_dict:
        if k not in stim_order:
            continue # skip this stimulus if don't need it for stim_order
        if sig.ndim == 2:
            specs = []
            for ch in range(sig.shape[1]):
                specs.append(aud_fn(sig[:,ch], fs, **aud_kwargs)[:,:,np.newaxis])
            spec = np.concatenate(specs, axis=-1)
        elif sig.ndim == 1:
            spec = aud_fn(sig, fs, **aud_kwargs)
        else:
            raise ValueError(f'Waveform to compute spectrogram for is more than 2 dimensional. Got {sig.ndim} dimensions')
        
        # resample to fs_out
        desired_len = int(fs_out / fs * len(sig))
        if desired_len != spec.shape[0]:
            spec = resample(spec, desired_len, axis=0)
        spec_dict[k] = spec
    
    output = [spec_dict[stim_name] for stim_name in stim_order]
    return output
    
def _load_stim_order(stim_order_path: str) -> List[str]:
    """
    Load either StimOrder.mat or StimOrder.txt file and return stimulus order as list of names
    
    Parameter
    ---------
    stim_order_path : str
        Path to file or directory containing file.
    
    Returns
    -------
    stim_order : List[str]
        Stimulus order as a list of stimulus names
    """

    if stim_order_path.endswith('.mat') or stim_order_path.endswith('.txt'):
        good_filepath = stim_order_path

    else:
        file_names = os.listdir(stim_order_path)
        found_file = False
        for fname in file_names:
            if fname == 'StimOrder.mat' or fname == 'StimOrder.txt':
                found_file = True
                good_filepath = os.path.join(stim_order_path, fname)
                break
        if not found_file:
            raise FileNotFoundError(f'Tried to find stim order file but could not find "StimOrder.mat" or "StimOrder.txt"'
                             f' within directory "{stim_order_path}". Must specify either a direct path to one of those files, or'
                             f' a directory containing at least one of them.')

    if good_filepath.endswith('.mat'):
        stim_order_dict = loadmat(good_filepath)
        if 'StimOrder' not in stim_order_dict:
            raise ValueError(f'Successfully StimOrder.mat but it did not contain a variable named "StimOrder"')
        stim_order = [x.item() for x in stim_order_dict['StimOrder'].squeeze()]
        return stim_order
    else:
        with open(good_filepath, 'r') as infile:
            lines = [x.strip() for x in infile.readlines()]
        return lines

    
def _split_data_on_alignment(data, fs, alignment_startstops, befaft, buffer_time=1):
    """
    data must be length 1, but can have as many fields as needed, each of which is a numpy array (time, ...)
    """
    output = {}
    for field in data.fields:
        split_field = []
        for align_region in alignment_startstops:
            start_time = align_region[0]-befaft[0]-buffer_time
            end_time = align_region[1]+befaft[1]+buffer_time
            start_sample = int(round(start_time * fs))
            end_sample = int(round(end_time * fs))
            split_field.append(data[0][field][start_sample:end_sample])
        output[field] = split_field
    
    return nlData(output)

def _remove_buffer_time(data, fs, buffer_time=1):
    output = {}
    buffer_samples = round(fs*buffer_time)
    for trial in range(len(data)):
        for field in data.fields:
            data[trial][field] = data[trial][field][buffer_samples:-buffer_samples]
    return data


def _verbosity(log_level) -> int:
    log_level = log_level.upper()
    if log_level == 'DEBUG':
        return 2
    elif log_level == 'INFO':
        return 1
    else:
        return 0


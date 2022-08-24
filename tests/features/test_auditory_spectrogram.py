import pytest
import numpy as np

from naplib.features import auditory_spectrogram

@pytest.fixture(scope='module')
def small_sound():
    fs = 10000
    t = 1
    f = 800
    samples = np.linspace(0, t, int(fs*t), endpoint=False)
    signal = np.sin(2 * np.pi * f * samples)
    return signal

def test_compare_matlab_small_sound_linear_factor(small_sound):
    aud = auditory_spectrogram(small_sound, 10000, frame_len=8, tc=4, factor='linear')
    aud_truth_last_row = np.array([0.00127752575430584, 0.000587155334613100, 0.000602010104545098, 0.00185327070321465, 0.00137293116058909, 0.000618488673062362, 0.00114732363025932, 0.00400709755765645, 0.00237473062750335, 0.00555400747727546, 0.00924259359983847, 0.00592726263684981, 0.0115446818806271, 0.0106439412779127, 0.0123767787614154, 0.0183176598780419, 0.0180367103390069, 0.0272253638428226, 0.0235714082087079, 0.0282571607076718, 0.0309430042303441, 0.0325447460271595, 0.0376028106361617, 0.0372144079058541, 0.0386569289061036, 0.0384854751741350, 0.0387098305777849, 0.0372512608945502, 0.0351217737429715, 0.0370370913511166, 0.0339272921829714, 0.0350598228083151, 0.0335617369613356, 0.0330455017175804, 0.0325545102219319, 0.0321224738100809, 0.0317473844410598, 0.0311107810257091, 0.0315187801496226, 0.0322292665787950, 0.0351492259347612, 0.0359729862660272, 0.0449327262530128, 0.0614890631486109, 0.0756043996470033, 0.0930556699643899, 0.110685946260308, 0.123998314472513, 0.135532369680317, 0.136591801712455, 0.137370599250710, 0.137732609498704, 0.134181264010945, 0.140908229312882, 0.145728078337763, 0.144558964303156, 0.156698751926567, 0.167865087355855, 0.224803501246933, 0.282332189225508, 0.369973984170780, 0.462999765877781, 0.547391684598095, 0.640680446900899, 1.00769496475514, 2.74696539589337, 7.07209992558219, 7.80122809608282, 4.50926240144048, 2.98870133192801, 1.96775434540470, 1.42542648475339, 1.05392959823808, 0.900248848987444, 0.795064818650369, 0.706080859721854, 0.581857429922898, 0.487531615127296, 0.419446637280516, 0.361729028889324, 0.339836987954194, 0.350462235443721, 0.299363892900544, 0.266055354266128, 0.233814481793288, 0.211779190210986, 0.211341939056874, 0.206021728791674, 0.184493430266619, 0.164383443256941, 0.151118191206701, 0.154736985597446, 0.146770421426899, 0.132395260368759, 0.122477649813866, 0.121627967837776, 0.118912171448799, 0.108811261803113, 0.100919691234896, 0.102195680577365, 0.0969131901783137, 0.0895638828315957, 0.0869935420070413, 0.0852956620391220, 0.0790234475498973, 0.0747799396891665, 0.0894345993206146, 0.0660366372727534, 0.0694991671196276, 0.0672466437042855, 0.0615373641454444, 0.0622929245938536, 0.0604982654378922, 0.0571816200309851, 0.0559117832616696, 0.0526765638156364, 0.0518461026324704, 0.0495253922229464, 0.0501246356513012, 0.0472104494496698, 0.0462406430336036, 0.0445707005236158, 0.0445837213659546, 0.0427808965710352, 0.0422267659272659, 0.0419218588758148, 0.0409006513536718, 0.0410055740483788])
    assert np.allclose(aud[-1,:], aud_truth_last_row, rtol=1e-6)

def test_compare_matlab_small_sound_halfwave_factor(small_sound):
    aud = auditory_spectrogram(small_sound, 10000, frame_len=8, tc=4, factor='half-wave')
    aud_truth_last_row = np.array([2.05403039703766e-106, 0.000425419501085653, 2.02158353335884e-106, 6.94264924050342e-111, 1.42866859481120e-113, 0.000587538543725441, 0.000853792397798515, 0.00271891043772899, 0.00174026872192609, 0.00709689184514391, 0.0148857968013286, 0.0107702089354360, 0.0233269868837258, 0.0236744175893597, 0.0300240836545789, 0.0446332660166917, 0.0421168117369265, 0.0586098041593283, 0.0445639437000449, 0.0500434819429852, 0.0492446622007364, 0.0456191828727236, 0.0514870693778663, 0.0459494760120542, 0.0457968439642490, 0.0438546666483901, 0.0446433246692476, 0.0426118844728126, 0.0394364120991959, 0.0431004469243995, 0.0384740037355521, 0.0396976262182915, 0.0364403552166990, 0.0357123339518178, 0.0352910075358841, 0.0351324758334314, 0.0325173560723557, 0.0309032918175867, 0.0320994413596819, 0.0318250418850367, 0.0309186144775545, 0.0284056004541283, 0.0316866893355955, 0.0513650134657351, 0.0851158419309611, 0.104869483673048, 0.127609409446485, 0.134388463814858, 0.142822812045966, 0.144339096735228, 0.145554423781327, 0.143845463401677, 0.143354347394082, 0.138021970973715, 0.135378858587624, 0.114483241383814, 0.128317482617277, 0.0997800063418325, 0.114555913196724, 0.154848898025934, 0.182186672002081, 0.207475728169192, 0.172450938132171, 0.0863733195076030, 0.0862849883220656, 1.02029050028536e-135, 0.997306307344068, 11.0320634365872, 8.54959805757474, 6.23218330231422, 4.60290883686999, 3.42737158664348, 2.48106655597887, 1.97038012697872, 1.64333568692607, 1.44315371271639, 1.20285285035313, 1.05356294190137, 0.893835840890658, 0.773686019458209, 0.677020469324895, 0.593673127749826, 0.557198746817899, 0.508304056245130, 0.474500940244240, 0.364593584754835, 0.354725519143078, 0.334737606528380, 0.298471088750923, 0.250170518800764, 0.236933263453548, 0.223476309915445, 0.207603603535616, 0.187639248840511, 0.190335570555043, 0.165350145999160, 0.142350372652042, 0.142543290343394, 0.142127595632607, 0.123129972957106, 0.123113759331734, 0.110001823066532, 0.103145879823924, 0.0973398301581371, 0.0946163442928859, 0.0768054436002053, 0.131907541627747, 0.0334797431295542, 0.0802681032530874, 0.0883322099529448, 0.0771004009559867, 0.0644773891059235, 0.0626555268670049, 0.0577608215251416, 0.0604115075713878, 0.0541692806694529, 0.0536272376436608, 0.0529777231644975, 0.0563105016798631, 0.0470859235153610, 0.0449318994591439, 0.0457322476432553, 0.0465630076536044, 0.0413821075574980, 0.0413824448712688, 0.0378183393827118, 0.0342372612801160, 0.0366026679803532])
    assert np.allclose(aud[-1,:], aud_truth_last_row, rtol=1e-6)

def test_compare_matlab_small_sound_point1_factor(small_sound):
    aud = auditory_spectrogram(small_sound, 10000, frame_len=8, tc=4, factor=0.1)
    aud_truth_100th_row = np.array([0.0153287910493139, 0.0129365283565109, 0.0118589281204903, 0.0218813744097483, 0.0157413125578812, 0.0118345385400656, 0.0170618131255687, 0.0246806035438584, 0.0114557392797160, 0.0208211276468260, 0.0360547417217092, 0.0269885515167704, 0.0292444013680735, 0.0120940658894378, 0.0172345709899905, 0.0293541971554301, 0.0155073280658341, 0.0567466053420488, 0.0157058532447347, 0.0192417476865407, 0.0188524536498723, 0.0119916104969108, 0.0378534804696706, 0.0176713638585359, 0.0218763439726428, 0.0178308993260177, 0.0289865480911347, 0.0246669302739793, 0.0109336271598152, 0.0431622063270946, 0.0164055737632840, 0.0404049465616950, 0.0299917612746143, 0.0309503086009817, 0.0325412403213242, 0.0339624834923601, 0.0354502313323486, 0.0319868079393362, 0.0447057217073202, 0.0547222093966253, 0.0697866683872864, 0.0400595035748002, 0.0434257456126631, 0.0615838064488328, 0.0529279938872625, 0.0481590548651192, 0.0597907459599840, 0.0634356855145343, 0.0648325311008975, 0.0733244811201457, 0.0869977084152016, 0.0904581564603785, 0.0646967225049110, 0.118786899698545, 0.163519267922486, 0.163117861842459, 0.172172837284850, 0.277112600867877, 0.395322140244062, 0.344380661334525, 0.395321623883606, 0.477229204182990, 0.508664117844378, 0.493906936863776, 1.84273982639183, 6.40379344738309, 10.3311321813041, 12.3712301348479, 7.72701651280186, 5.82805774128594, 4.13926410712661, 3.29675700634076, 2.59006136816237, 2.20582820725712, 1.96723544976995, 1.72308109186371, 1.29770209635915, 1.27320411853150, 1.12315615742299, 0.982684209919281, 0.626594715566759, 1.00354438291619, 0.678929369854832, 0.606383556760521, 0.547138547961139, 0.494801827315818, 0.449777208192504, 0.410647418675884, 0.376460678447959, 0.347126983862374, 0.321625296545201, 0.301145138202132, 0.279632556239069, 0.260804838742480, 0.249402536290441, 0.231362528981181, 0.219986620274699, 0.205462343220337, 0.202286095745210, 0.189105088747044, 0.184684014558262, 0.170946284703249, 0.173905935170822, 0.157434888143481, 0.162588422136179, 0.0866897777903200, 0.320518391535545, 0.0526861480125642, 0.154071845749191, 0.151009628064158, 0.140491900538043, 0.122750048509847, 0.161129923409159, 0.138168792335127, 0.135439324383785, 0.137909382461266, 0.135432885571936, 0.130988368646640, 0.140946234947824, 0.133472499999721, 0.136609410159017, 0.135434754060071, 0.137605799880839, 0.137275014661282, 0.138928330004541, 0.141260153175969, 0.135209356036896, 0.161882634183045])
    assert np.allclose(aud[99,:], aud_truth_100th_row, rtol=1e-6)


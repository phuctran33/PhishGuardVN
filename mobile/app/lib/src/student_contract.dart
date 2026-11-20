/// Frozen Student Android MLP int8 v1 contract from Phuc's PR #35.
const String studentModelSchema = 'android-student-char-tfidf-mlp-int8-v1';
const String studentModelVersion = 'student-mlp-kd-int8-v1';
const String studentDecisionRule = 'score >= threshold';
const String studentScoreKind = 'uncalibrated_sigmoid';
const double studentThreshold = 0.72961075;

const int studentModelBytes = 283334;
const String studentModelSha256 =
    '8d118ac5346543bdfa29b7970b48ae206305d5fe8992e0c4754aa070cc032341';

const int studentPslBytes = 75007;
const String studentPslSha256 =
    'fb8419c17a533dfdd57199da1cef1481974119fe23ce7c478af3d12eb8466c8f';

const String studentTeacherModelVersion = 'teacher-stacking-v2';
const String studentTeacherBundleSha256 =
    '63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1';
const String studentTeacherLockSha256 =
    '781e1670a96df52b830bc40eb40af046d47db5f0a1b963bd2d42195c740db96c';

const String studentResearchRevision =
    '8389b371728d4aab8246c0cf9606eb788a8e0365';
const String studentResearchFingerprint =
    'e2b3068ec55ceea49772c4233b33405cbbf7aba6831cfd496d89e6b33feb227b';

const String studentManifestAsset = 'assets/student_mlp_manifest.json';
const String studentModelAsset = 'assets/student_mlp.json.gz';
const String studentPslAsset = 'assets/psl_icann_tldextract_5.4.0.txt';

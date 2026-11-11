import { useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Ionicons } from '@expo/vector-icons';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { colors } from '../theme';

// Temporary phone-camera preview for UI testing; final pose validation comes from the bag.
const poses = ['front', 'right', 'back', 'left'];
const avatarImages = {
  male: {
    front: require('../../assets/characters/male-front.png'),
    right: require('../../assets/characters/male-right.png'),
    back: require('../../assets/characters/male-back.png'),
    left: require('../../assets/characters/male-left.png'),
  },
  female: {
    front: require('../../assets/characters/female-front.png'),
    right: require('../../assets/characters/female-right.png'),
    back: require('../../assets/characters/female-back.png'),
    left: require('../../assets/characters/female-left.png'),
  },
};

function FaceAvatar({ pose, gender }) {
  return <View style={a.stage}>
    <View style={a.glow} />
    <Image source={avatarImages[gender][pose]} resizeMode="contain" style={a.character} />
    <View style={a.direction}><Ionicons name={pose === 'front' ? 'scan-outline' : pose === 'back' ? 'person-outline' : pose === 'right' ? 'arrow-forward' : 'arrow-back'} size={17} color={colors.primary} /></View>
  </View>;
}

export default function FaceSetupScreen({ navigation }) {
  const { t, isRTL } = useLanguage();
  const { user } = useAuth();
  const isFocused = useIsFocused();
  const [permission, requestPermission] = useCameraPermissions();
  const [step, setStep] = useState(0);
  const [cameraError, setCameraError] = useState(false);
  const done = step >= poses.length;
  const pose = poses[Math.min(step, poses.length - 1)];
  const align = { textAlign: isRTL ? 'right' : 'left' };

  return <ScrollView style={s.screen} contentContainerStyle={s.content}>
    <Pressable onPress={() => navigation.goBack()} style={[s.back, { alignSelf: isRTL ? 'flex-start' : 'flex-end' }]} accessibilityRole="button" accessibilityLabel={t('back')}>
      <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={22} color={colors.text} />
    </Pressable>
    <Text style={[s.title, align]}>{t('faceSetupTitle')}</Text>
    <Text style={[s.subtitle, align]}>{t('phoneSetupHint')}</Text>

    <View style={s.modePill}><View style={s.modeDot} /><Text style={s.modeText}>{t('phoneCameraTest')}</Text></View>
    <View style={s.cameraFrame}>
      {permission?.granted && isFocused ? <CameraView
        style={StyleSheet.absoluteFill}
        facing="front"
        mirror
        onMountError={() => setCameraError(true)}
      /> : null}
      {!permission ? <View style={s.cameraMessage}><ActivityIndicator color={colors.primary} /><Text style={s.cameraMessageText}>{t('cameraStarting')}</Text></View>
        : !permission.granted ? <View style={s.cameraMessage}><View style={s.cameraIcon}><Ionicons name="camera-outline" size={25} color={colors.primary} /></View><Text style={s.cameraMessageText}>{t('cameraPermissionHint')}</Text><Pressable style={s.primaryButton} onPress={requestPermission}><Text style={s.primaryButtonText}>{t('cameraPermissionAction')}</Text></Pressable></View>
          : cameraError ? <View style={s.cameraMessage}><Ionicons name="alert-circle-outline" size={30} color={colors.danger} /><Text style={s.cameraMessageText}>{t('cameraError')}</Text><Pressable onPress={() => setCameraError(false)}><Text style={s.retryText}>{t('retry')}</Text></Pressable></View>
            : <View pointerEvents="none" style={s.cameraOverlay}><View style={s.cameraTopPill}><View style={s.liveDot} /><Text style={s.cameraTopText}>{t('cameraLive')}</Text></View><View style={s.frameGuide} /></View>}
    </View>

    {done ? <View style={s.doneCard}>
      <View style={s.doneIcon}><Ionicons name="checkmark-done" size={29} color={colors.success} /></View>
      <Text style={s.doneTitle}>{t('faceSetupDone')}</Text>
      <Text style={[s.doneHint, align]}>{t('phoneSetupDoneHint')}</Text>
      <Pressable style={s.primaryButton} onPress={() => setStep(0)}><Text style={s.primaryButtonText}>{t('faceSetupRestart')}</Text></Pressable>
    </View> : <>
      <View style={s.stepRow}>{poses.map((item, i) => {
        const isDone = i < step;
        const isCurrent = i === step;
        return <View key={item} style={s.stepItem}><View style={[s.stepDot, isDone && s.stepDone, isCurrent && s.stepCurrent]}>{isDone ? <Ionicons name="checkmark" size={13} color="#fff" /> : <Text style={[s.stepNumber, isCurrent && s.stepNumberCurrent]}>{i + 1}</Text>}</View><Text style={[s.stepLabel, isCurrent && s.stepLabelCurrent]}>{t(`pose_${item}`)}</Text></View>;
      })}</View>
      <View style={s.avatarCard}>
        <View style={[s.guideBadge, { alignSelf: isRTL ? 'flex-end' : 'flex-start' }]}><Text style={s.guideBadgeText}>{t('poseStep', { current: step + 1 })}</Text></View>
        <FaceAvatar pose={pose} gender={user?.gender === 'female' ? 'female' : 'male'} />
        <Text style={[s.poseTitle, align]}>{t(`pose_${pose}`)}</Text>
        <Text style={[s.poseHint, align]}>{t(`poseHint_${pose}`)}</Text>
        <View style={s.manualNote}><Ionicons name="information-circle-outline" size={18} color={colors.accent} /><Text style={s.manualNoteText}>{t('phonePoseManual')}</Text></View>
        <Pressable style={s.primaryButton} onPress={() => setStep((current) => current + 1)}><Text style={s.primaryButtonText}>{step === poses.length - 1 ? t('finishPoseTest') : t('nextPose')}</Text><Ionicons name={isRTL ? 'arrow-back' : 'arrow-forward'} size={18} color="#fff" /></Pressable>
      </View>
    </>}
  </ScrollView>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg }, content: { padding: 20, paddingBottom: 36 }, back: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card, borderRadius: 15, marginBottom: 16 },
  title: { color: colors.text, fontSize: 25, fontWeight: '800', marginBottom: 6 }, subtitle: { color: colors.muted, fontSize: 14, lineHeight: 21, marginBottom: 12 },
  modePill: { alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 7, backgroundColor: colors.softGold, borderRadius: 16, paddingVertical: 7, paddingHorizontal: 11, marginBottom: 13 }, modeDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.accent }, modeText: { color: '#916318', fontSize: 11, fontWeight: '800' },
  cameraFrame: { height: 245, borderRadius: 23, overflow: 'hidden', backgroundColor: '#DCE7E2', alignItems: 'center', justifyContent: 'center', marginBottom: 18 }, cameraMessage: { alignItems: 'center', justifyContent: 'center', padding: 24, gap: 12 }, cameraMessageText: { color: colors.text, fontSize: 13, lineHeight: 20, fontWeight: '600', textAlign: 'center' }, cameraIcon: { width: 54, height: 54, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.softGreen }, cameraOverlay: { ...StyleSheet.absoluteFillObject, justifyContent: 'space-between', alignItems: 'center', padding: 12 }, cameraTopPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(20,35,31,0.68)', paddingHorizontal: 11, paddingVertical: 7, borderRadius: 16, alignSelf: 'flex-end' }, cameraTopText: { color: '#fff', fontSize: 10, fontWeight: '800' }, liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#6FE0A2' }, frameGuide: { width: 164, height: 198, borderColor: 'rgba(255,255,255,0.85)', borderWidth: 1.5, borderRadius: 80, marginBottom: 4 }, retryText: { color: colors.primary, fontWeight: '800', padding: 8 },
  stepRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 17 }, stepItem: { alignItems: 'center', flex: 1 }, stepDot: { width: 29, height: 29, borderRadius: 15, borderWidth: 1.5, borderColor: colors.border, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card }, stepDone: { backgroundColor: colors.success, borderColor: colors.success }, stepCurrent: { borderColor: colors.primary, backgroundColor: colors.softGreen }, stepNumber: { fontSize: 12, fontWeight: '700', color: colors.muted }, stepNumberCurrent: { color: colors.primary }, stepLabel: { fontSize: 10, color: colors.muted, marginTop: 5 }, stepLabelCurrent: { color: colors.primary, fontWeight: '800' },
  avatarCard: { padding: 18, backgroundColor: colors.card, borderRadius: 25, borderWidth: 1, borderColor: colors.border, alignItems: 'stretch' }, guideBadge: { backgroundColor: colors.softGold, paddingVertical: 6, paddingHorizontal: 11, borderRadius: 20 }, guideBadgeText: { color: '#916318', fontSize: 11, fontWeight: '800' }, poseTitle: { color: colors.text, fontSize: 19, fontWeight: '800', marginTop: 13 }, poseHint: { color: colors.muted, fontSize: 13, lineHeight: 20, marginTop: 5 }, manualNote: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.softGold, padding: 11, borderRadius: 13, marginTop: 14 }, manualNoteText: { flex: 1, color: colors.text, fontWeight: '600', fontSize: 12, lineHeight: 18 }, primaryButton: { minHeight: 48, alignSelf: 'stretch', marginTop: 15, borderRadius: 14, backgroundColor: colors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 }, primaryButtonText: { color: '#fff', fontWeight: '800', fontSize: 14 },
  doneCard: { padding: 24, borderRadius: 24, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, alignItems: 'center' }, doneIcon: { width: 62, height: 62, borderRadius: 22, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center' }, doneTitle: { color: colors.text, fontSize: 17, fontWeight: '800', textAlign: 'center', marginTop: 13 }, doneHint: { color: colors.muted, fontSize: 13, lineHeight: 20, marginTop: 7 },
});

const a = StyleSheet.create({
  stage: { height: 238, marginTop: 13, borderRadius: 20, backgroundColor: '#F1F7F4', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }, glow: { position: 'absolute', top: 27, width: 180, height: 180, borderRadius: 90, backgroundColor: '#DFEFE8' },
  character: { width: 128, height: 224 },
  direction: { position: 'absolute', bottom: 10, right: 11, width: 34, height: 34, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff' },
});

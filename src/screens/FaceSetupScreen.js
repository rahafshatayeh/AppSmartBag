import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { getFollowInfo, getFollowSnapshotSource, getFollowThumbSource, startFaceRegistration } from '../services/api';
import { colors } from '../theme';
import LiveCamera from '../components/LiveCamera';

// Matches REGISTER_STEPS in the Raspberry Pi service: front, back, right, left.
const poses = ['front', 'back', 'right', 'left'];
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
  const direction = pose === 'front' ? 'scan-outline' : pose === 'back' ? 'person-outline' : pose === 'right' ? 'arrow-forward' : 'arrow-back';
  return <View style={a.stage}>
    <View style={a.glow} />
    <Image source={avatarImages[gender][pose]} resizeMode="contain" style={a.character} />
    <View style={a.direction}><Ionicons name={direction} size={17} color={colors.primary} /></View>
  </View>;
}

export default function FaceSetupScreen({ navigation }) {
  const { t, isRTL } = useLanguage();
  const { user } = useAuth();
  const isFocused = useIsFocused();
  const [bagInfo, setBagInfo] = useState(null);
  const [capturedImages, setCapturedImages] = useState({});
  const [cameraSource, setCameraSource] = useState(null);
  const [cameraFrameSource, setCameraFrameSource] = useState(null);
  const [streamStarted, setStreamStarted] = useState(false);
  const [starting, setStarting] = useState(false);
  const [connectionError, setConnectionError] = useState(false);
  const [cameraError, setCameraError] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const lastThumbVersion = useRef(null);
  const frameTimer = useRef(null);
  const frameVersion = useRef(0);
  const align = { textAlign: isRTL ? 'right' : 'left' };
  const total = Number(bagInfo?.reg_total) || poses.length;
  const captured = Math.max(0, Math.min(Number(bagInfo?.reg_done) || 0, total));
  const done = captured >= total && captured > 0;
  const step = done ? total - 1 : Math.min(captured, poses.length - 1);
  const pose = poses[step];

  const scheduleNextSnapshot = useCallback((delay = 100) => {
    clearTimeout(frameTimer.current);
    if (!isFocused || !streamStarted || !cameraSource) return;
    frameTimer.current = setTimeout(() => {
      frameVersion.current += 1;
      setCameraFrameSource({ ...cameraSource, uri: `${cameraSource.uri}?frame=${frameVersion.current}` });
    }, delay);
  }, [isFocused, streamStarted, cameraSource]);

  // البث صار من مكوّن LiveCamera (شغّال دايماً وأنتِ على الشاشة)
  useEffect(() => () => clearTimeout(frameTimer.current), []);

  useEffect(() => {
    if (!isFocused) return undefined;
    let cancelled = false;
    let timer;

    const poll = async () => {
      try {
        const info = await getFollowInfo();
        if (cancelled) return;
        setBagInfo(info);
        setStarting(false);
        setConnectionError(false);
        const thumbVersion = Number(info.thumb_ver) || 0;
        if (lastThumbVersion.current !== thumbVersion) {
          lastThumbVersion.current = thumbVersion;
          const indices = Array.isArray(info.thumbs) ? info.thumbs.map(Number).filter((index) => index >= 0 && index < poses.length) : [];
          if (!indices.length) setCapturedImages({});
          else Promise.all(indices.map(async (index) => [poses[index], await getFollowThumbSource(index, thumbVersion)]))
            .then((entries) => { if (!cancelled) setCapturedImages(Object.fromEntries(entries)); })
            .catch(() => {});
        }
        if (info.reg_active) {
          setStreamStarted(true);
          if (!cameraSource) {
            try { setCameraSource(await getFollowSnapshotSource()); setCameraLoading(true); }
            catch { setCameraError(true); }
          }
        }
        const shouldContinue = Boolean(info.reg_active) || (streamStarted && !done);
        if (shouldContinue && !cancelled) timer = setTimeout(poll, 850);
      } catch {
        if (cancelled) return;
        setConnectionError(true);
        if ((streamStarted || starting) && !cancelled) timer = setTimeout(poll, 1500);
      }
    };

    poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [isFocused, streamStarted, starting, cameraSource, done]);

  const beginRegistration = async () => {
    setBusy(true);
    setCameraError(false);
    setCameraLoading(true);
    setConnectionError(false);
    try {
      await startFaceRegistration();
      setBagInfo(null);
      setCapturedImages({});
      lastThumbVersion.current = null;
      setStarting(true);
      setStreamStarted(true);
      const source = await getFollowSnapshotSource();
      setCameraSource(source);
    } catch {
      setConnectionError(true);
    } finally {
      setBusy(false);
    }
  };

  return <ScrollView style={s.screen} contentContainerStyle={s.content}>
    <Pressable onPress={() => navigation.goBack()} style={[s.back, { alignSelf: isRTL ? 'flex-start' : 'flex-end' }]} accessibilityRole="button" accessibilityLabel={t('back')}>
      <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={22} color={colors.text} />
    </Pressable>
    <Text style={[s.title, align]}>{t('faceSetupTitle')}</Text>
    <Text style={[s.subtitle, align]}>{t('followSetupHint')}</Text>

    <View style={s.modePill}><View style={s.modeDot} /><Text style={s.modeText}>{t('followBagCamera')}</Text></View>
    <LiveCamera height={245} style={{ marginBottom: 18 }} />

    {streamStarted ? <>
      <View style={s.stepRow}>{poses.map((item, index) => {
        const isDone = index < captured;
        const isCurrent = !done && index === step;
        const photo = capturedImages[item];
        return <View key={item} style={s.stepItem}><View style={[s.stepThumb, isCurrent && s.stepCurrent]}>{photo ? <Image source={photo} resizeMode="cover" style={s.stepPhoto} /> : isDone ? <Ionicons name="checkmark" size={17} color={colors.success} /> : <Text style={[s.stepNumber, isCurrent && s.stepNumberCurrent]}>{index + 1}</Text>}</View><Text style={[s.stepLabel, isCurrent && s.stepLabelCurrent]}>{t(`pose_${item}`)}</Text></View>;
      })}</View>
      <View style={s.avatarCard}>
        <View style={[s.guideBadge, { alignSelf: isRTL ? 'flex-end' : 'flex-start' }]}><Text style={s.guideBadgeText}>{t('poseStep', { current: Math.min(captured + 1, total) })}</Text></View>
        <FaceAvatar pose={pose} gender={user?.gender === 'female' ? 'female' : 'male'} />
        <Text style={[s.poseTitle, align]}>{done ? t('faceSetupDone') : t(`pose_${pose}`)}</Text>
        <Text style={[s.poseHint, align]}>{done ? t('faceSetupDoneHint') : t(`poseHint_${pose}`)}</Text>
        {!done && <View style={[s.statusNote, bagInfo?.reg_warn && s.warningNote]}>
          <Ionicons name={bagInfo?.reg_warn ? 'alert-circle-outline' : 'information-circle-outline'} size={18} color={bagInfo?.reg_warn ? colors.danger : colors.accent} />
          <Text style={[s.statusNoteText, bagInfo?.reg_warn && s.warningText]}>{bagInfo?.reg_warn ? t('personNotDetected') : Number(bagInfo?.pause_left) > 0 ? t('followStarting') : t('poseWaitingForPi')}</Text>
        </View>}
      </View>
      {connectionError && <Text style={[s.connectionHint, align]}>{t('networkFailure')}</Text>}
      {done && <Pressable style={s.primaryButton} onPress={beginRegistration} disabled={busy}><Text style={s.primaryButtonText}>{busy ? t('followStarting') : t('faceSetupRestart')}</Text></Pressable>}
    </> : <>
      <View style={s.avatarCard}>
        <View style={[s.guideBadge, { alignSelf: isRTL ? 'flex-end' : 'flex-start' }]}><Text style={s.guideBadgeText}>{t('poseStep', { current: 1 })}</Text></View>
        <FaceAvatar pose="front" gender={user?.gender === 'female' ? 'female' : 'male'} />
        <Text style={[s.poseTitle, align]}>{t('pose_front')}</Text>
        <Text style={[s.poseHint, align]}>{t('followInactive')}</Text>
      </View>
      <Pressable style={[s.primaryButton, busy && s.buttonDisabled]} onPress={beginRegistration} disabled={busy}>
        {busy ? <ActivityIndicator color="#fff" /> : <Ionicons name="camera" size={18} color="#fff" />}
        <Text style={s.primaryButtonText}>{busy ? t('followStarting') : t('faceSetupStart')}</Text>
      </Pressable>
      {connectionError && <Text style={[s.connectionHint, align]}>{t('followStartError')}</Text>}
    </>}
  </ScrollView>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg }, content: { padding: 20, paddingBottom: 36 }, back: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card, borderRadius: 15, marginBottom: 16 },
  title: { color: colors.text, fontSize: 25, fontWeight: '800', marginBottom: 6 }, subtitle: { color: colors.muted, fontSize: 14, lineHeight: 21, marginBottom: 12 },
  modePill: { alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 7, backgroundColor: colors.softGold, borderRadius: 16, paddingVertical: 7, paddingHorizontal: 11, marginBottom: 13 }, modeDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.accent }, modeText: { color: '#916318', fontSize: 11, fontWeight: '800' },
  cameraFrame: { height: 245, borderRadius: 23, overflow: 'hidden', backgroundColor: '#DCE7E2', alignItems: 'center', justifyContent: 'center', marginBottom: 18 }, cameraStream: { width: '100%', height: '100%', backgroundColor: '#17211E' }, cameraWaiting: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: 'rgba(220,231,226,0.85)' }, cameraWaitingText: { color: colors.text, fontSize: 12, fontWeight: '700' }, cameraFailure: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 20, backgroundColor: 'rgba(220,231,226,0.9)' }, cameraMessage: { alignItems: 'center', justifyContent: 'center', padding: 24, gap: 12 }, cameraMessageText: { color: colors.text, fontSize: 13, lineHeight: 20, fontWeight: '600', textAlign: 'center' }, cameraIcon: { width: 54, height: 54, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.softGreen }, liveBadge: { position: 'absolute', top: 11, right: 11, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(20,35,31,0.72)', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 16 }, liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#6FE0A2' }, liveDotConnecting: { backgroundColor: '#FFC56B' }, liveText: { color: '#fff', fontSize: 10, fontWeight: '800' }, retryText: { color: colors.primary, fontWeight: '800', padding: 8 },
  stepRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 17 }, stepItem: { alignItems: 'center', flex: 1 }, stepThumb: { width: 50, height: 60, borderRadius: 12, borderWidth: 1.5, borderColor: colors.border, alignItems: 'center', justifyContent: 'center', overflow: 'hidden', backgroundColor: colors.card }, stepPhoto: { width: '100%', height: '100%' }, stepCurrent: { borderColor: colors.primary, backgroundColor: colors.softGreen }, stepNumber: { fontSize: 12, fontWeight: '700', color: colors.muted }, stepNumberCurrent: { color: colors.primary }, stepLabel: { fontSize: 10, color: colors.muted, marginTop: 5 }, stepLabelCurrent: { color: colors.primary, fontWeight: '800' },
  avatarCard: { padding: 18, backgroundColor: colors.card, borderRadius: 25, borderWidth: 1, borderColor: colors.border, alignItems: 'stretch' }, guideBadge: { backgroundColor: colors.softGold, paddingVertical: 6, paddingHorizontal: 11, borderRadius: 20 }, guideBadgeText: { color: '#916318', fontSize: 11, fontWeight: '800' }, poseTitle: { color: colors.text, fontSize: 19, fontWeight: '800', marginTop: 13 }, poseHint: { color: colors.muted, fontSize: 13, lineHeight: 20, marginTop: 5 }, statusNote: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.softGold, padding: 11, borderRadius: 13, marginTop: 14 }, statusNoteText: { flex: 1, color: colors.text, fontWeight: '600', fontSize: 12, lineHeight: 18 }, warningNote: { backgroundColor: '#FFF0EF' }, warningText: { color: colors.danger }, primaryButton: { minHeight: 48, alignSelf: 'stretch', marginTop: 15, borderRadius: 14, backgroundColor: colors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 }, primaryButtonText: { color: '#fff', fontWeight: '800', fontSize: 14 }, buttonDisabled: { opacity: 0.7 }, connectionHint: { color: colors.danger, fontSize: 12, marginTop: 10, lineHeight: 18 },
});

const a = StyleSheet.create({
  stage: { height: 238, marginTop: 13, borderRadius: 20, backgroundColor: '#F1F7F4', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }, glow: { position: 'absolute', top: 27, width: 180, height: 180, borderRadius: 90, backgroundColor: '#DFEFE8' },
  character: { width: 128, height: 224 }, direction: { position: 'absolute', bottom: 10, right: 11, width: 34, height: 34, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff' },
});
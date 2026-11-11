import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, RefreshControl, Alert, Pressable } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import PrimaryButton from '../components/PrimaryButton';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { getStatus, lockBag, unlockBag } from '../services/api';
import { addLog, getLogs } from '../services/logStore';
import { colors } from '../theme';

const Metric = ({ icon, label, value, tint, isRTL }) => <View style={[s.metric, { alignItems: isRTL ? 'flex-end' : 'flex-start' }]}>
  <View style={[s.metricIcon, { backgroundColor: tint }]}><Ionicons name={icon} size={20} color={colors.primary} /></View>
  <Text style={s.metricValue}>{value}</Text><Text style={[s.metricLabel, { textAlign: isRTL ? 'right' : 'left' }]}>{label}</Text>
</View>;

export default function DashboardScreen({ navigation }) {
  const { user } = useAuth();
  const { t, isRTL } = useLanguage();
  const [status, setStatus] = useState(null);
  const [online, setOnline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [recent, setRecent] = useState(null);
  const load = useCallback(async () => {
    try { setStatus(await getStatus()); setOnline(true); } catch { setOnline(false); }
    try { setRecent((await getLogs())[0] || null); } catch { setRecent(null); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };
  const act = async (fn, label) => {
    setBusy(true);
    try { const data = await fn(); setStatus((previous) => ({ ...previous, ...data })); setOnline(true); await addLog(label, user?.name); setRecent((await getLogs())[0] || null); }
    catch (error) { setOnline(false); Alert.alert(t('connectionFailed'), t(error.message)); }
    finally { setBusy(false); }
  };
  const locked = status?.locked;
  const known = typeof locked === 'boolean';
  const show = (value, suffix = '') => value === null || value === undefined ? '—' : `${value}${suffix}`;
  const align = { textAlign: isRTL ? 'right' : 'left' };

  return <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}>
    <View style={[s.greetingRow, !isRTL && s.rowLtr]}>
      <View style={s.avatar}><Ionicons name="person" size={20} color={colors.primary} /></View>
      <View style={[s.greeting, { alignItems: isRTL ? 'flex-end' : 'flex-start' }]}><Text style={s.eyebrow}>{t('bagControl')}</Text><Text style={s.hello}>{t('greeting', { name: user?.name || '' })}</Text></View>
    </View>
    <Pressable style={[s.faceSetupCard, !isRTL && s.rowLtr]} onPress={() => navigation.navigate('FaceSetup')}>
      <View style={s.faceSetupIcon}><Ionicons name="scan" size={22} color={colors.primary} /></View>
      <View style={[s.faceSetupCopy, { alignItems: isRTL ? 'flex-end' : 'flex-start' }]}><Text style={[s.faceSetupTitle, align]}>{t('followSetupEntry')}</Text><Text style={[s.faceSetupHint, align]}>{t('followSetupEntryHint')}</Text></View>
      <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={18} color={colors.muted} />
    </Pressable>
    <View style={[s.statusCard, known && (locked ? s.lockedCard : s.unlockedCard)]}>
      <View style={[s.statusTop, !isRTL && s.rowLtr]}>
        <View style={[s.statusIcon, { backgroundColor: known && locked ? colors.softGreen : known ? colors.softRed : colors.softGold }]}><Ionicons name={!known ? 'help-circle' : locked ? 'lock-closed' : 'lock-open'} size={30} color={!known ? colors.accent : locked ? colors.success : colors.danger} /></View>
        <View style={[s.statusCopy, { alignItems: isRTL ? 'flex-end' : 'flex-start' }]}><Text style={s.statusLabel}>{t('bagStatus')}</Text><Text style={s.statusText}>{!known ? t('waiting') : locked ? t('locked') : t('unlocked')}</Text></View>
        <View style={[s.connectionPill, online ? s.onlinePill : s.offlinePill, !isRTL && s.rowLtr]}><View style={[s.dot, { backgroundColor: online ? colors.success : colors.muted }]} /><Text style={[s.connectionText, { color: online ? colors.success : colors.muted }]}>{online ? t('online') : t('offline')}</Text></View>
      </View>
      <View style={s.divider} /><Text style={[s.statusHint, align]}>{known ? (locked ? t('contentsSafe') : t('lockReminder')) : t('pullToRefresh')}</Text>
    </View>
    <Text style={[s.sectionTitle, align]}>{t('quickControl')}</Text>
    <View style={[s.actionRow, !isRTL && s.rowLtr]}>
      <PrimaryButton title={t('openBag')} color={colors.danger} style={s.actionButton} loading={busy} disabled={known && !locked} onPress={() => act(unlockBag, t('openBag'))} />
      <PrimaryButton title={t('lockBag')} color={colors.primary} style={s.actionButton} loading={busy} disabled={known && locked} onPress={() => act(lockBag, t('lockBag'))} />
    </View>
    <Text style={[s.sectionTitle, align]}>{t('bagInfo')}</Text>
    <View style={[s.metricsRow, !isRTL && s.rowLtr]}>
      <Metric icon="battery-half" label={t('battery')} value={show(status?.battery, '%')} tint={colors.softGreen} isRTL={isRTL} />
      <Metric icon="barbell" label={t('weight')} value={show(status?.weight, isRTL ? ' \u0643\u063a' : ' kg')} tint={colors.softGold} isRTL={isRTL} />
    </View>
    <Pressable style={[s.recentCard, !isRTL && s.rowLtr]} onPress={() => navigation.navigate('Log')}>
      <View style={s.recentIcon}><Ionicons name="time-outline" size={20} color={colors.primary} /></View>
      <View style={[s.recentCopy, { alignItems: isRTL ? 'flex-end' : 'flex-start' }]}><Text style={[s.recentLabel, align]}>{t('latest')}</Text><Text style={[s.recentText, align]} numberOfLines={1}>{recent?.action || t('noActivity')}</Text></View>
      <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={18} color={colors.muted} />
    </Pressable>
    <Text style={s.hint}>{t('refreshData')}</Text>
  </ScrollView>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg }, content: { padding: 20, paddingBottom: 32 },
  greetingRow: { flexDirection: 'row-reverse', alignItems: 'center', marginBottom: 22 }, rowLtr: { flexDirection: 'row' },
  faceSetupCard: { flexDirection: 'row-reverse', alignItems: 'center', backgroundColor: colors.card, borderRadius: 18, padding: 14, borderWidth: 1, borderColor: colors.border, marginBottom: 18 }, faceSetupIcon: { width: 42, height: 42, borderRadius: 14, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center' }, faceSetupCopy: { flex: 1, marginHorizontal: 10 }, faceSetupTitle: { color: colors.text, fontSize: 14, fontWeight: '800' }, faceSetupHint: { color: colors.muted, fontSize: 11, marginTop: 3 },
  avatar: { width: 46, height: 46, borderRadius: 16, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center' },
  greeting: { flex: 1, marginHorizontal: 12 }, eyebrow: { color: colors.muted, fontSize: 12, marginBottom: 2 }, hello: { color: colors.text, fontSize: 23, fontWeight: '800' },
  statusCard: { backgroundColor: colors.card, borderRadius: 24, padding: 20, marginBottom: 24, borderWidth: 1, borderColor: colors.border }, lockedCard: { borderColor: '#CFE8DF' }, unlockedCard: { borderColor: '#F2D7D7' },
  statusTop: { flexDirection: 'row-reverse', alignItems: 'center' }, statusIcon: { width: 56, height: 56, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  statusCopy: { flex: 1, marginHorizontal: 12 }, statusLabel: { color: colors.muted, fontSize: 13, marginBottom: 4 }, statusText: { color: colors.text, fontSize: 18, fontWeight: '800' },
  connectionPill: { flexDirection: 'row-reverse', alignItems: 'center', borderRadius: 20, paddingVertical: 6, paddingHorizontal: 9, gap: 5 }, onlinePill: { backgroundColor: colors.softGreen }, offlinePill: { backgroundColor: colors.bg }, dot: { width: 7, height: 7, borderRadius: 4 }, connectionText: { fontSize: 11, fontWeight: '700' },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: 16 }, statusHint: { color: colors.muted, fontSize: 13 }, sectionTitle: { color: colors.text, fontSize: 17, fontWeight: '800', marginBottom: 12 },
  actionRow: { flexDirection: 'row', gap: 10, marginBottom: 24 }, actionButton: { flex: 1, marginTop: 0, minHeight: 50 }, metricsRow: { flexDirection: 'row', gap: 12, marginBottom: 18 },
  metric: { flex: 1, backgroundColor: colors.card, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: colors.border }, metricIcon: { width: 38, height: 38, borderRadius: 13, alignItems: 'center', justifyContent: 'center', marginBottom: 14 }, metricValue: { color: colors.text, fontSize: 22, fontWeight: '800', marginBottom: 3 }, metricLabel: { color: colors.muted, fontSize: 12 },
  recentCard: { flexDirection: 'row-reverse', alignItems: 'center', backgroundColor: colors.card, borderRadius: 18, padding: 14, borderWidth: 1, borderColor: colors.border }, recentIcon: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center' }, recentCopy: { flex: 1, marginHorizontal: 10 }, recentLabel: { color: colors.muted, fontSize: 11, marginBottom: 3 }, recentText: { color: colors.text, fontSize: 13, fontWeight: '700' }, hint: { color: colors.muted, textAlign: 'center', fontSize: 12, marginTop: 18 },
});

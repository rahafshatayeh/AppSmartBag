import { useCallback, useState } from 'react';
import { View, Text, FlatList, StyleSheet, Pressable } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { getLogs, clearLogs } from '../services/logStore';
import { useLanguage } from '../context/LanguageContext';
import { colors } from '../theme';

export default function LogScreen() {
  const { t, isRTL, language } = useLanguage();
  const [logs, setLogs] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(async () => setLogs(await getLogs()), []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const clear = async () => { await clearLogs(); setLogs([]); };
  const align = { textAlign: isRTL ? 'right' : 'left' };
  return <View style={s.container}><FlatList
    data={logs} keyExtractor={(item) => item.id} contentContainerStyle={s.list}
    refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }}
    ListHeaderComponent={<View style={[s.header, { alignItems: isRTL ? 'flex-end' : 'flex-start' }]}><Text style={s.title}>{t('activityTitle')}</Text><Text style={s.subtitle}>{t('activitySubtitle')}</Text></View>}
    ListEmptyComponent={<View style={s.emptyState}><View style={s.emptyIcon}><Ionicons name="time-outline" size={28} color={colors.primary} /></View><Text style={s.emptyTitle}>{t('emptyActivity')}</Text><Text style={s.empty}>{t('emptyActivityHint')}</Text></View>}
    renderItem={({ item }) => {
      const date = new Date(item.time);
      const time = Number.isNaN(date.getTime()) ? item.time : date.toLocaleString(language === 'ar' ? 'ar' : 'en-US');
      return <View style={[s.item, !isRTL && s.itemLtr]}><View style={s.iconBox}><Ionicons name="lock-closed-outline" size={19} color={colors.primary} /></View><View style={[s.itemCopy, { alignItems: isRTL ? 'flex-end' : 'flex-start' }]}><Text style={[s.action, align]}>{item.action}</Text><Text style={[s.meta, align]}>{item.who}  •  {time}</Text></View></View>;
    }}
    ListFooterComponent={logs.length > 0 ? <Pressable onPress={clear} style={s.clearButton}><Ionicons name="trash-outline" size={16} color={colors.danger} /><Text style={s.clear}>{t('clearLog')}</Text></Pressable> : null}
  /></View>;
}
const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg }, list: { padding: 18, paddingBottom: 30, flexGrow: 1 }, header: { marginBottom: 20 },
  title: { color: colors.text, fontSize: 23, fontWeight: '900' }, subtitle: { color: colors.muted, fontSize: 13, marginTop: 5 },
  item: { flexDirection: 'row-reverse', alignItems: 'center', backgroundColor: colors.card, borderRadius: 17, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: colors.border }, itemLtr: { flexDirection: 'row' },
  iconBox: { width: 42, height: 42, borderRadius: 14, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center' }, itemCopy: { flex: 1, marginHorizontal: 12 }, action: { color: colors.text, fontSize: 14, fontWeight: '700' }, meta: { color: colors.muted, fontSize: 11, marginTop: 5 },
  emptyState: { alignItems: 'center', marginTop: 80, paddingHorizontal: 24 }, emptyIcon: { backgroundColor: colors.softGreen, width: 64, height: 64, borderRadius: 22, alignItems: 'center', justifyContent: 'center', marginBottom: 14 }, emptyTitle: { color: colors.text, fontWeight: '800', fontSize: 17, marginBottom: 6 }, empty: { color: colors.muted, textAlign: 'center', lineHeight: 20 },
  clearButton: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 7, padding: 16, marginTop: 6 }, clear: { color: colors.danger, fontWeight: '700' },
});

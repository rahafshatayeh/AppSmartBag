import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, Alert } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import Input from '../components/Input';
import PrimaryButton from '../components/PrimaryButton';
import { getPackingItems, savePackingItems } from '../services/packingStore';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { colors } from '../theme';

const suggestedItems = [
  { en: 'glasses', ar: '\u0646\u0638\u0627\u0631\u0627\u062a' },
  { en: 'sunglasses', ar: '\u0646\u0638\u0627\u0631\u0627\u062a \u0634\u0645\u0633\u064a\u0629' },
  { en: 'reading glasses', ar: '\u0646\u0638\u0627\u0631\u0627\u062a \u0642\u0631\u0627\u0621\u0629' },
  { en: 'glass bottle', ar: '\u0632\u062c\u0627\u062c\u0629 \u0632\u062c\u0627\u062c\u064a\u0629' },
  { en: 'charger', ar: '\u0634\u0627\u062d\u0646' },
  { en: 'phone', ar: '\u0647\u0627\u062a\u0641' },
  { en: 'wallet', ar: '\u0645\u062d\u0641\u0638\u0629' },
  { en: 'keys', ar: '\u0645\u0641\u0627\u062a\u064a\u062d' },
  { en: 'passport', ar: '\u062c\u0648\u0627\u0632 \u0633\u0641\u0631' },
  { en: 'water bottle', ar: '\u0632\u062c\u0627\u062c\u0629 \u0645\u0627\u0621' },
  { en: 'headphones', ar: '\u0633\u0645\u0627\u0639\u0627\u062a' },
  { en: 'umbrella', ar: '\u0645\u0638\u0644\u0629' },
  { en: 'laptop', ar: '\u062d\u0627\u0633\u0648\u0628 \u0645\u062d\u0645\u0648\u0644' },
  { en: 'medication', ar: '\u0623\u062f\u0648\u064a\u0629' },
  { en: 'book', ar: '\u0643\u062a\u0627\u0628' },
];

export default function PackingListScreen() {
  const { t, isRTL, language } = useLanguage();
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [draft, setDraft] = useState('');
  const load = useCallback(async () => setItems(await getPackingItems(user?.email)), [user?.email]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const add = async (suggestion = draft) => {
    const value = suggestion.trim();
    if (!value) return Alert.alert(t('alert'), t('itemRequired'));
    const next = [{ id: `${Date.now()}`, title: value, done: false }, ...items];
    setItems(next); setDraft(''); await savePackingItems(next, user?.email);
  };
  const query = draft.trim().toLocaleLowerCase();
  const suggestions = query.length < 2 ? [] : suggestedItems
    .map((item) => item[language])
    .filter((item) => item.toLocaleLowerCase().includes(query))
    .filter((item) => !items.some((existing) => existing.title.toLocaleLowerCase() === item.toLocaleLowerCase()))
    .slice(0, 5);
  const toggle = async (id) => {
    const next = items.map((item) => item.id === id ? { ...item, done: !item.done } : item);
    setItems(next); await savePackingItems(next, user?.email);
  };
  const remove = async (id) => {
    const next = items.filter((item) => item.id !== id);
    setItems(next); await savePackingItems(next, user?.email);
  };

  return <View style={s.screen}>
    <FlatList
      data={items}
      keyExtractor={(item) => item.id}
      contentContainerStyle={[s.list, items.length === 0 && s.emptyList]}
      ListHeaderComponent={<View style={s.header}><Text style={[s.title, { textAlign: isRTL ? 'right' : 'left' }]}>{t('packingTitle')}</Text><Text style={[s.hint, { textAlign: isRTL ? 'right' : 'left' }]}>{t('packingHint')}</Text><View style={[s.addRow, isRTL ? null : s.addRowLtr]}><Input placeholder={t('itemPlaceholder')} value={draft} onChangeText={setDraft} onSubmitEditing={add} returnKeyType="done" style={[s.input, { textAlign: isRTL ? 'right' : 'left' }]} /><PrimaryButton title={t('addItem')} onPress={() => add()} style={s.addButton} /></View>{suggestions.length > 0 && <View style={s.suggestionWrap}><Text style={[s.suggestionLabel, { textAlign: isRTL ? 'right' : 'left' }]}>{t('suggestions')}</Text><View style={[s.suggestionList, !isRTL && s.addRowLtr]}>{suggestions.map((item) => <Pressable key={item} onPress={() => add(item)} style={s.suggestion}><Ionicons name="add-circle-outline" size={16} color={colors.primary} /><Text style={s.suggestionText}>{item}</Text></Pressable>)}</View></View>}{items.length > 0 && <Text style={[s.counter, { textAlign: isRTL ? 'right' : 'left' }]}>{t('remaining', { count: items.filter((item) => !item.done).length })}</Text>}</View>}
      ListEmptyComponent={<View style={s.empty}><View style={s.emptyIcon}><Ionicons name="bag-handle-outline" size={29} color={colors.primary} /></View><Text style={s.emptyTitle}>{t('emptyPacking')}</Text><Text style={s.emptyHint}>{t('emptyPackingHint')}</Text></View>}
      renderItem={({ item }) => <View style={[s.item, isRTL ? null : s.itemLtr]}>
        <Pressable onPress={() => toggle(item.id)} style={[s.check, item.done && s.checked]} accessibilityRole="checkbox" accessibilityState={{ checked: item.done }}><Ionicons name={item.done ? 'checkmark' : 'ellipse-outline'} size={20} color={item.done ? '#fff' : colors.muted} /></Pressable>
        <Text style={[s.itemTitle, item.done && s.done, { textAlign: isRTL ? 'right' : 'left' }]}>{item.title}</Text>
        <Pressable onPress={() => remove(item.id)} hitSlop={8} style={s.delete}><Ionicons name="trash-outline" size={18} color={colors.danger} /></Pressable>
      </View>}
    />
  </View>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  list: { padding: 18, paddingBottom: 28 },
  emptyList: { flexGrow: 1 },
  header: { marginBottom: 16 },
  title: { color: colors.text, fontSize: 23, fontWeight: '900' },
  hint: { color: colors.muted, marginTop: 5, marginBottom: 17, lineHeight: 20 },
  addRow: { flexDirection: 'row-reverse', alignItems: 'flex-start', gap: 9 },
  addRowLtr: { flexDirection: 'row' },
  input: { flex: 1, minWidth: 0, marginBottom: 0 },
  addButton: { marginTop: 0, paddingHorizontal: 14 },
  suggestionWrap: { marginTop: 7, marginBottom: 6 },
  suggestionLabel: { color: colors.muted, fontSize: 11, fontWeight: '700', marginBottom: 7 },
  suggestionList: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: 7 },
  suggestion: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: colors.softGreen, borderRadius: 16, paddingVertical: 8, paddingHorizontal: 11 },
  suggestionText: { color: colors.primaryDark, fontSize: 12, fontWeight: '700' },
  counter: { color: colors.primary, fontSize: 12, fontWeight: '700', marginTop: 5 },
  item: { flexDirection: 'row-reverse', alignItems: 'center', backgroundColor: colors.card, borderRadius: 17, padding: 13, marginBottom: 9, borderWidth: 1, borderColor: colors.border },
  itemLtr: { flexDirection: 'row' },
  check: { width: 29, height: 29, borderRadius: 10, borderWidth: 1.5, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  checked: { backgroundColor: colors.primary, borderColor: colors.primary },
  itemTitle: { flex: 1, color: colors.text, fontSize: 15, marginHorizontal: 12 },
  done: { color: colors.muted, textDecorationLine: 'line-through' },
  delete: { padding: 5 },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 25, paddingBottom: 45 },
  emptyIcon: { width: 68, height: 68, borderRadius: 23, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center', marginBottom: 14 },
  emptyTitle: { color: colors.text, fontWeight: '800', fontSize: 17, marginBottom: 6 },
  emptyHint: { color: colors.muted, textAlign: 'center', lineHeight: 20 },
});

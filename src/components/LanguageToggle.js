import { View, Pressable, Text, StyleSheet } from 'react-native';
import { useLanguage } from '../context/LanguageContext';
import { colors } from '../theme';

export default function LanguageToggle() {
  const { language, setLanguage } = useLanguage();
  const item = (code, label) => (
    <Pressable key={code} onPress={() => setLanguage(code)} style={[s.item, language === code && s.active]}>
      <Text style={[s.text, language === code && s.activeText]}>{label}</Text>
    </Pressable>
  );
  return <View style={s.row}>{item('ar', 'العربية')}{item('en', 'English')}</View>;
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignSelf: 'center', backgroundColor: colors.card, borderRadius: 20, borderWidth: 1, borderColor: colors.border, padding: 4, marginBottom: 18, gap: 4 },
  item: { paddingVertical: 7, paddingHorizontal: 16, borderRadius: 16 },
  active: { backgroundColor: colors.primary },
  text: { color: colors.muted, fontWeight: '700', fontSize: 13 },
  activeText: { color: '#fff' },
});

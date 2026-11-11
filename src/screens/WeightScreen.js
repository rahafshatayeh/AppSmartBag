import { useCallback, useRef, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TextInput, Alert, KeyboardAvoidingView, Platform, Vibration } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import PrimaryButton from '../components/PrimaryButton';
import { useLanguage } from '../context/LanguageContext';
import { getWeight, setWeightLimit } from '../services/api';
import { colors } from '../theme';

const STR = {
  ar: {
    title: 'وزن الحقيبة', subtitle: 'القراءة مباشرة من حساسات الوزن بالحقيبة',
    kg: 'كغم', total: 'الوزن الحالي', limit: 'الحد المسموح',
    online: 'متصل', offline: 'غير متصل', stable: 'ثابت', moving: 'بتتحرك…', settling: 'بيستقر…',
    overTitle: '⚠️ تخطيت الوزن المسموح', overBody: 'الوزن الحالي {kg} كغم، والحد المسموح {limit} كغم. لازم تشيل {diff} كغم.',
    remaining: 'باقي {n} كغم للحد المسموح', noConnection: 'ما في اتصال بالحقيبة. تأكد إنك على نفس شبكة الحقيبة.',
    limitTitle: 'الحد المسموح', limitHint: 'اكتب أقصى وزن مسموح للحقيبة (مثلاً 23 كغم للطيارة).', limitPlaceholder: 'الحد المسموح بالكيلو', save: 'حفظ',
    done: 'تم ✅', saved: 'تم حفظ الحد المسموح.', error: 'خطأ', enterNumber: 'اكتب رقم صحيح أكبر من صفر',
  },
  en: {
    title: 'Bag weight', subtitle: 'Live reading from the bag load cells',
    kg: 'kg', total: 'Current weight', limit: 'Weight limit',
    online: 'Connected', offline: 'Offline', stable: 'Stable', moving: 'Moving…', settling: 'Settling…',
    overTitle: '⚠️ Weight limit exceeded', overBody: 'Current weight is {kg} kg and the limit is {limit} kg. Remove {diff} kg.',
    remaining: '{n} kg left to the limit', noConnection: 'No connection to the bag. Make sure you are on the same network as the bag.',
    limitTitle: 'Weight limit', limitHint: 'Enter the maximum allowed bag weight (e.g. 23 kg for flights).', limitPlaceholder: 'Limit in kg', save: 'Save',
    done: 'Done ✅', saved: 'Weight limit saved.', error: 'Error', enterNumber: 'Enter a valid number above zero',
  },
};

const num = (v) => { const n = parseFloat(String(v).replace(',', '.')); return Number.isFinite(n) ? n : null; };

export default function WeightScreen() {
  const { language, isRTL } = useLanguage();
  const L = STR[language] || STR.ar;
  const tr = (k, vals = {}) => Object.entries(vals).reduce((r, [n, v]) => r.replace(`{${n}}`, String(v)), L[k] || k);
  const [w, setW] = useState(null);
  const [online, setOnline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [limitKg, setLimitKg] = useState('');
  const filled = useRef(false);
  const wasOver = useRef(false);
  const LRef = useRef(L);
  LRef.current = L;

  const load = useCallback(async () => {
    try {
      const data = await getWeight();
      setW(data); setOnline(true);
      if (!filled.current) { setLimitKg(String(data.limit ?? '')); filled.current = true; }
      // تنبيه مرة وحدة لما الوزن يتخطى الحد (وبيرجع ينبّه إذا نزل وبعدين رجع تخطى)
      if (data.over && !wasOver.current) {
        const T = LRef.current;
        const fill = (s) => s.replace('{kg}', data.kg.toFixed(2)).replace('{limit}', data.limit).replace('{diff}', (data.kg - data.limit).toFixed(2));
        Vibration.vibrate(600);
        Alert.alert(T.overTitle, fill(T.overBody));
      }
      wasOver.current = !!data.over;
    } catch { setOnline(false); }
  }, []);

  useFocusEffect(useCallback(() => {          // تحديث كل ثانية وإنت على هالشاشة
    load();
    const id = setInterval(load, 1000);
    return () => clearInterval(id);
  }, [load]));

  const saveLimit = async () => {
    const v = num(limitKg);
    if (v == null || v <= 0) return Alert.alert(L.error, L.enterNumber);
    setBusy(true);
    try { await setWeightLimit(v); wasOver.current = false; Alert.alert(L.done, L.saved); await load(); }
    catch (e) { Alert.alert(L.error, e.message === 'timeout' || e.message === 'networkFailure' ? L.noConnection : e.message); }
    finally { setBusy(false); }
  };

  const align = { textAlign: isRTL ? 'right' : 'left' };
  const row = [s.row, !isRTL && s.rowLtr];
  const kg = w?.kg;
  const limit = w?.limit || 23;
  const over = !!w?.over;
  const pct = kg == null ? 0 : Math.min(1, kg / limit);
  const barColor = over ? colors.danger : pct > 0.85 ? colors.accent : colors.success;
  const pill = !online ? { t: L.offline, c: colors.muted, bg: colors.bg }
    : w?.moving ? { t: L.moving, c: colors.accent, bg: colors.softGold }
    : w?.stable ? { t: L.stable, c: colors.success, bg: colors.softGreen }
    : { t: L.settling, c: colors.muted, bg: colors.bg };

  return <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <ScrollView style={s.screen} contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
      <Text style={[s.title, align]}>{L.title}</Text>
      <Text style={[s.subtitle, align]}>{L.subtitle}</Text>

      {over && <View style={[s.overBanner, !isRTL && s.rowLtr]}>
        <Ionicons name="warning" size={26} color="#fff" />
        <View style={{ flex: 1, marginHorizontal: 10 }}>
          <Text style={[s.overTitle, align]}>{L.overTitle}</Text>
          <Text style={[s.overBody, align]}>{tr('overBody', { kg: kg.toFixed(2), limit, diff: (kg - limit).toFixed(2) })}</Text>
        </View>
      </View>}

      <View style={[s.card, over && s.cardOver]}>
        <View style={row}>
          <View style={[s.bigIcon, { backgroundColor: over ? colors.softRed : colors.softGold }]}>
            <Ionicons name="barbell" size={30} color={over ? colors.danger : colors.accent} />
          </View>
          <View style={[s.flex, { alignItems: isRTL ? 'flex-end' : 'flex-start', marginHorizontal: 12 }]}>
            <Text style={s.label}>{L.total}</Text>
            <Text style={[s.big, over && { color: colors.danger }]}>{kg == null ? '—' : kg.toFixed(2)} <Text style={s.unit}>{L.kg}</Text></Text>
          </View>
          <View style={[s.pill, { backgroundColor: pill.bg }]}><Text style={[s.pillText, { color: pill.c }]}>{pill.t}</Text></View>
        </View>

        <View style={s.barBg}><View style={[s.barFill, { width: `${Math.round(pct * 100)}%`, backgroundColor: barColor }]} /></View>
        {kg != null && !over && <Text style={[s.note, align, { color: colors.muted }]}>{tr('remaining', { n: (limit - kg).toFixed(2) })}</Text>}
        {!online && <Text style={[s.note, align, { color: colors.danger }]}>{L.noConnection}</Text>}
        {online && !!w?.err && <Text style={[s.note, align, { color: colors.danger }]}>{w.err}</Text>}

        <View style={s.divider} />
        <View style={row}><Text style={s.k}>{L.limit}</Text><Text style={s.v}>{w ? `${limit} ${L.kg}` : '—'}</Text></View>
      </View>

      <View style={s.card}>
        <Text style={[s.section, align]}>{L.limitTitle}</Text>
        <Text style={[s.hint, align]}>{L.limitHint}</Text>
        <TextInput style={[s.input, align]} value={limitKg} onChangeText={setLimitKg} placeholder={L.limitPlaceholder} placeholderTextColor={colors.muted} keyboardType="decimal-pad" />
        <PrimaryButton title={L.save} loading={busy} disabled={!online || busy} onPress={saveLimit} />
      </View>
    </ScrollView>
  </KeyboardAvoidingView>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg }, content: { padding: 20, paddingBottom: 40 }, flex: { flex: 1 },
  title: { color: colors.text, fontSize: 24, fontWeight: '800' }, subtitle: { color: colors.muted, fontSize: 13, marginTop: 4, marginBottom: 18 },
  overBanner: { flexDirection: 'row-reverse', alignItems: 'center', backgroundColor: colors.danger, borderRadius: 18, padding: 16, marginBottom: 16 },
  overTitle: { color: '#fff', fontSize: 17, fontWeight: '800' }, overBody: { color: '#fff', fontSize: 13, marginTop: 4 },
  card: { backgroundColor: colors.card, borderRadius: 22, padding: 18, marginBottom: 16, borderWidth: 1, borderColor: colors.border }, cardOver: { borderColor: colors.danger, borderWidth: 2 },
  row: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', marginVertical: 3 }, rowLtr: { flexDirection: 'row' },
  bigIcon: { width: 58, height: 58, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  label: { color: colors.muted, fontSize: 13, marginBottom: 2 }, big: { color: colors.text, fontSize: 38, fontWeight: '800' }, unit: { fontSize: 16, color: colors.muted, fontWeight: '700' },
  pill: { borderRadius: 20, paddingVertical: 6, paddingHorizontal: 10, maxWidth: 130 }, pillText: { fontSize: 11, fontWeight: '800', textAlign: 'center' },
  barBg: { height: 10, borderRadius: 6, backgroundColor: colors.bg, marginTop: 16, overflow: 'hidden' }, barFill: { height: 10, borderRadius: 6 },
  note: { fontSize: 13, marginTop: 8, fontWeight: '600' }, divider: { height: 1, backgroundColor: colors.border, marginVertical: 14 },
  k: { color: colors.muted, fontSize: 14 }, v: { color: colors.text, fontSize: 15, fontWeight: '800' },
  section: { color: colors.text, fontSize: 16, fontWeight: '800', marginBottom: 4 }, hint: { color: colors.muted, fontSize: 13, marginBottom: 10 },
  input: { backgroundColor: colors.bg, borderRadius: 14, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, color: colors.text, marginBottom: 10 },
});
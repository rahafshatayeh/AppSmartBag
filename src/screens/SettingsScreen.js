import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, Alert, ScrollView, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Input from '../components/Input';
import PrimaryButton from '../components/PrimaryButton';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { getConfig, saveConfig, getStatus } from '../services/api';
import { colors } from '../theme';

export default function SettingsScreen() {
  const { logout } = useAuth();
  const { language, setLanguage, t, isRTL } = useLanguage();
  const [ip, setIp] = useState('');
  const [token, setToken] = useState('');
  const [testing, setTesting] = useState(false);
  useEffect(() => { getConfig().then((config) => { setIp(config.ip); setToken(config.token); }); }, []);
  const save = async () => {
    try { await saveConfig({ ip: ip.trim(), token }); Alert.alert(t('saved')); }
    catch { Alert.alert(t('settings'), t('saveFailed')); }
  };
  const test = async () => {
    setTesting(true);
    try { await saveConfig({ ip: ip.trim(), token }); await getStatus(); Alert.alert(t('connection'), t('connectionSuccess')); }
    catch (error) { Alert.alert(t('connectionFailed'), t(error.message)); }
    finally { setTesting(false); }
  };
  const languageOption = (code, label) => <Pressable onPress={() => setLanguage(code)} style={[s.languageOption, language === code && s.selectedLanguage]}>
    <Ionicons name={language === code ? 'checkmark-circle' : 'ellipse-outline'} size={20} color={language === code ? colors.primary : colors.muted} />
    <Text style={[s.languageText, language === code && s.selectedLanguageText]}>{label}</Text>
  </Pressable>;

  return <ScrollView style={s.screen} contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
    <Text style={[s.intro, { textAlign: isRTL ? 'right' : 'left' }]}>{t('settingsIntro')}</Text>
    <View style={s.card}>
      <View style={[s.heading, isRTL ? null : s.headingLtr]}><View style={s.iconBox}><Ionicons name="language-outline" size={20} color={colors.primary} /></View><Text style={s.headingText}>{t('language')}</Text></View>
      <Text style={[s.help, { textAlign: isRTL ? 'right' : 'left' }]}>{t('chooseLanguage')}</Text>
      <View style={s.languageRow}>{languageOption('ar', t('arabic'))}{languageOption('en', t('english'))}</View>
    </View>
    <View style={s.card}>
      <View style={[s.heading, isRTL ? null : s.headingLtr]}><View style={[s.iconBox, { backgroundColor: colors.softGold }]}><Ionicons name="wifi-outline" size={20} color={colors.accent} /></View><Text style={s.headingText}>{t('connection')}</Text></View>
      <Text style={[s.help, { textAlign: isRTL ? 'right' : 'left' }]}>{t('connectionHelp')}</Text>
      <Input placeholder="192.168.137.7" keyboardType="url" autoCorrect={false} value={ip} onChangeText={setIp} style={{ textAlign: 'left' }} />
      <Input placeholder={t('token')} value={token} onChangeText={setToken} style={{ textAlign: isRTL ? 'right' : 'left' }} />
      <PrimaryButton title={t('save')} onPress={save} />
      <PrimaryButton title={t('testConnection')} color={colors.card} textColor={colors.primary} onPress={test} loading={testing} style={s.secondaryButton} />
    </View>
    <PrimaryButton title={t('logout')} color={colors.softRed} onPress={logout} style={s.logout} textColor={colors.danger} />
  </ScrollView>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: 18, paddingBottom: 30 },
  intro: { color: colors.muted, fontSize: 14, marginBottom: 18, lineHeight: 21 },
  card: { backgroundColor: colors.card, borderRadius: 22, padding: 18, marginBottom: 14, borderWidth: 1, borderColor: colors.border },
  heading: { flexDirection: 'row-reverse', alignItems: 'center', marginBottom: 15 },
  headingLtr: { flexDirection: 'row' },
  iconBox: { width: 38, height: 38, borderRadius: 13, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center', marginHorizontal: 10 },
  headingText: { color: colors.text, fontWeight: '800', fontSize: 16 },
  help: { color: colors.muted, fontSize: 12, marginBottom: 14, lineHeight: 19 },
  languageRow: { flexDirection: 'row', gap: 10 },
  languageOption: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, minHeight: 48, borderWidth: 1, borderColor: colors.border, borderRadius: 14 },
  selectedLanguage: { backgroundColor: colors.softGreen, borderColor: colors.primary },
  languageText: { color: colors.muted, fontWeight: '700' },
  selectedLanguageText: { color: colors.primary },
  secondaryButton: { borderWidth: 1, borderColor: colors.border, marginTop: 10 },
  logout: { marginTop: 8 },
});
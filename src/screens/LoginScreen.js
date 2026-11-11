import { useState } from 'react';
import { View, Text, StyleSheet, Alert, Pressable, KeyboardAvoidingView, Platform, ScrollView, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Input from '../components/Input';
import PrimaryButton from '../components/PrimaryButton';
import LanguageToggle from '../components/LanguageToggle';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { colors } from '../theme';

export default function LoginScreen({ navigation }) {
  const { login } = useAuth();
  const { t, isRTL } = useLanguage();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [gender, setGender] = useState(null);
  const [loading, setLoading] = useState(false);
  const align = { textAlign: isRTL ? 'right' : 'left' };
  const submit = async () => {
    if (!email || !password) return Alert.alert(t('alert'), t('fillFields'));
    if (!gender) return Alert.alert(t('alert'), t('genderRequired'));
    setLoading(true);
    try { await login(email, password, gender); }
    catch (error) { Alert.alert(t('login'), t(error.message)); setLoading(false); }
  };
  return <KeyboardAvoidingView style={s.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
    <LanguageToggle />
    <View style={s.brandMark}><Ionicons name="briefcase" size={38} color={colors.primary} /></View>
    <Text style={s.title}>Smart Bag</Text><Text style={s.sub}>{t('brandLine')}</Text>
    <View style={s.form}><Text style={[s.formTitle, align]}>{t('welcome')}</Text><Text style={[s.formHint, align]}>{t('loginHint')}</Text>
      <Input placeholder={t('email')} keyboardType="email-address" value={email} onChangeText={setEmail} style={{ textAlign: 'left' }} />
      <Input placeholder={t('password')} secureTextEntry value={password} onChangeText={setPassword} style={align} />
      <Text style={[s.genderTitle, align]}>{t('genderQuestion')}</Text>
      <View style={s.genderRow}>
        {['male', 'female'].map((item) => <Pressable key={item} onPress={() => setGender(item)} accessibilityRole="button" accessibilityState={{ selected: gender === item }} style={[s.genderOption, gender === item && s.genderSelected]}>
          <Image source={item === 'male' ? require('../../assets/characters/male-front-transparent.png') : require('../../assets/characters/female-front-transparent.png')} resizeMode="contain" style={s.genderImage} />
          <Text style={[s.genderLabel, gender === item && s.genderLabelSelected]}>{t(item)}</Text>
        </Pressable>)}
      </View>
      <PrimaryButton title={t('login')} onPress={submit} loading={loading} />
    </View>
    <Pressable onPress={() => navigation.navigate('Register')} style={s.footer}><Text style={s.footerText}>{t('noAccount')} <Text style={s.link}>{t('createAccount')}</Text></Text></Pressable>
    </ScrollView>
  </KeyboardAvoidingView>;
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg }, content: { flexGrow: 1, justifyContent: 'center', padding: 24 },
  brandMark: { alignSelf: 'center', width: 76, height: 76, borderRadius: 25, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  title: { color: colors.text, fontSize: 30, fontWeight: '900', textAlign: 'center' }, sub: { color: colors.muted, textAlign: 'center', marginTop: 5, marginBottom: 28, fontSize: 14 },
  form: { backgroundColor: colors.card, borderRadius: 24, padding: 20, borderWidth: 1, borderColor: colors.border }, formTitle: { color: colors.text, fontSize: 20, fontWeight: '800' }, formHint: { color: colors.muted, fontSize: 13, marginTop: 5, marginBottom: 20 }, genderTitle: { color: colors.text, fontSize: 13, fontWeight: '800', marginTop: 5, marginBottom: 9 }, genderRow: { flexDirection: 'row', gap: 10, marginBottom: 15 }, genderOption: { flex: 1, minHeight: 74, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderWidth: 1, borderColor: colors.border, borderRadius: 15, backgroundColor: '#FAFCFB' }, genderSelected: { borderColor: colors.primary, backgroundColor: colors.softGreen }, genderImage: { width: 32, height: 62 }, genderLabel: { color: colors.text, fontSize: 13, fontWeight: '700' }, genderLabelSelected: { color: colors.primaryDark },
  footer: { marginTop: 22, padding: 8 }, footerText: { color: colors.muted, textAlign: 'center', fontSize: 14 }, link: { color: colors.primary, fontWeight: '800' },
});

import { useState } from 'react';
import { View, Text, StyleSheet, Alert, Pressable, ScrollView, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Input from '../components/Input';
import PrimaryButton from '../components/PrimaryButton';
import LanguageToggle from '../components/LanguageToggle';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { colors } from '../theme';

export default function RegisterScreen({ navigation }) {
  const { register } = useAuth();
  const { t, isRTL } = useLanguage();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [gender, setGender] = useState(null);
  const [loading, setLoading] = useState(false);
  const align = { textAlign: isRTL ? 'right' : 'left' };
  const submit = async () => {
    if (!name.trim() || !email.trim() || !password) return Alert.alert(t('alert'), t('fillFields'));
    if (!gender) return Alert.alert(t('alert'), t('genderRequired'));
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return Alert.alert(t('alert'), t('invalidEmail'));
    if (password.length < 6) return Alert.alert(t('alert'), t('shortPassword'));
    if (password !== confirm) return Alert.alert(t('alert'), t('passwordMismatch'));
    setLoading(true);
    try { await register(name, email, password, gender); }
    catch (error) { Alert.alert(t('register'), t(error.message)); setLoading(false); }
  };
  return <ScrollView style={s.screen} contentContainerStyle={s.container} keyboardShouldPersistTaps="handled">
    <LanguageToggle />
    <View style={s.brandMark}><Ionicons name="person-add" size={28} color={colors.primary} /></View>
    <Text style={s.title}>{t('newAccount')}</Text><Text style={s.subtitle}>{t('registerHint')}</Text>
    <View style={s.form}>
      <Input placeholder={t('name')} value={name} onChangeText={setName} autoCapitalize="words" style={align} />
      <Input placeholder={t('email')} keyboardType="email-address" value={email} onChangeText={setEmail} style={{ textAlign: 'left' }} />
      <Input placeholder={t('password')} secureTextEntry value={password} onChangeText={setPassword} style={align} />
      <Input placeholder={t('confirmPassword')} secureTextEntry value={confirm} onChangeText={setConfirm} style={align} />
      <Text style={[s.genderTitle, align]}>{t('genderQuestion')}</Text>
      <View style={s.genderRow}>
        {['male', 'female'].map((item) => <Pressable key={item} onPress={() => setGender(item)} accessibilityRole="button" accessibilityState={{ selected: gender === item }} style={[s.genderOption, gender === item && s.genderSelected]}>
          <Image source={item === 'male' ? require('../../assets/characters/male-front-transparent.png') : require('../../assets/characters/female-front-transparent.png')} resizeMode="contain" style={s.genderImage} />
          <Text style={[s.genderLabel, gender === item && s.genderLabelSelected]}>{t(item)}</Text>
        </Pressable>)}
      </View>
      <PrimaryButton title={t('register')} onPress={submit} loading={loading} />
    </View>
    <Pressable onPress={() => navigation.goBack()} style={s.footer}><Text style={s.footerText}>{t('hasAccount')} <Text style={s.link}>{t('login')}</Text></Text></Pressable>
  </ScrollView>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg }, container: { flexGrow: 1, justifyContent: 'center', padding: 24 },
  brandMark: { alignSelf: 'center', width: 62, height: 62, borderRadius: 20, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center', marginBottom: 14 },
  title: { color: colors.text, fontSize: 27, fontWeight: '900', textAlign: 'center' }, subtitle: { color: colors.muted, textAlign: 'center', marginTop: 6, marginBottom: 24 },
  form: { backgroundColor: colors.card, borderRadius: 24, padding: 18, borderWidth: 1, borderColor: colors.border }, genderTitle: { color: colors.text, fontSize: 13, fontWeight: '800', marginTop: 4, marginBottom: 9 }, genderRow: { flexDirection: 'row', gap: 10, marginBottom: 15 }, genderOption: { flex: 1, minHeight: 74, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderWidth: 1, borderColor: colors.border, borderRadius: 15, backgroundColor: '#FAFCFB' }, genderSelected: { borderColor: colors.primary, backgroundColor: colors.softGreen }, genderImage: { width: 32, height: 62 }, genderLabel: { color: colors.text, fontSize: 13, fontWeight: '700' }, genderLabelSelected: { color: colors.primaryDark }, footer: { marginTop: 20, padding: 8 }, footerText: { color: colors.muted, textAlign: 'center', fontSize: 14 }, link: { color: colors.primary, fontWeight: '800' },
});

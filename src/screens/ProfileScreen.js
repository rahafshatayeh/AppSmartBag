import { useState } from 'react';
import { View, Text, StyleSheet, Alert, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Input from '../components/Input';
import PrimaryButton from '../components/PrimaryButton';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { colors } from '../theme';

export default function ProfileScreen() {
  const { user, updateProfile } = useAuth();
  const { t, isRTL } = useLanguage();
  const [name, setName] = useState(user?.name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!name.trim() || !email.trim()) return Alert.alert(t('alert'), t('fillFields'));
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return Alert.alert(t('alert'), t('invalidEmail'));
    setSaving(true);
    try { await updateProfile(name, email); Alert.alert(t('profileTitle'), t('profileSaved')); }
    catch (error) { Alert.alert(t('profileTitle'), t(error.message) || t('saveFailed')); }
    finally { setSaving(false); }
  };

  return <ScrollView style={s.screen} contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
    <View style={s.hero}>
      <View style={s.avatar}><Ionicons name="person" size={34} color={colors.primary} /></View>
      <Text style={s.title}>{t('profileTitle')}</Text>
      <Text style={s.subtitle}>{t('editProfile')}</Text>
    </View>
    <View style={s.card}>
      <Text style={[s.label, { textAlign: isRTL ? 'right' : 'left' }]}>{t('name')}</Text>
      <Input placeholder={t('name')} value={name} onChangeText={setName} autoCapitalize="words" style={{ textAlign: isRTL ? 'right' : 'left' }} />
      <Text style={[s.label, { textAlign: isRTL ? 'right' : 'left' }]}>{t('email')}</Text>
      <Input placeholder={t('email')} keyboardType="email-address" value={email} onChangeText={setEmail} style={{ textAlign: 'left' }} />
      <PrimaryButton title={t('saveProfile')} onPress={save} loading={saving} />
    </View>
  </ScrollView>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: 20 },
  hero: { alignItems: 'center', marginBottom: 22, marginTop: 8 },
  avatar: { width: 82, height: 82, borderRadius: 28, backgroundColor: colors.softGreen, alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  title: { fontSize: 23, fontWeight: '900', color: colors.text },
  subtitle: { color: colors.muted, marginTop: 5 },
  card: { padding: 20, backgroundColor: colors.card, borderRadius: 22, borderWidth: 1, borderColor: colors.border },
  label: { fontSize: 13, color: colors.muted, marginBottom: 7, fontWeight: '700' },
});

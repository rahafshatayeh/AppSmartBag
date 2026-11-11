import { TextInput, StyleSheet } from 'react-native';
import { colors } from '../theme';

export default function Input({ style, ...props }) {
  return <TextInput placeholderTextColor={colors.muted} autoCapitalize="none" {...props} style={[s.input, style]} />;
}

const s = StyleSheet.create({
  input: {
    backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14,
    paddingHorizontal: 14, paddingVertical: 13, fontSize: 15, color: colors.text, marginBottom: 12,
  },
});

import { Pressable, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { colors } from '../theme';

export default function PrimaryButton({ title, onPress, color, textColor = '#fff', loading, disabled, style }) {
  const off = loading || disabled;
  return (
    <Pressable
      onPress={onPress}
      disabled={off}
      style={[s.btn, { backgroundColor: color || colors.primary, opacity: off ? 0.55 : 1 }, style]}
    >
      {loading ? (
        <ActivityIndicator color="#fff" />
      ) : (
        <Text style={[s.text, { color: textColor }]}>{title}</Text>
      )}
    </Pressable>
  );
}

const s = StyleSheet.create({
  btn: { paddingHorizontal: 16, paddingVertical: 15, borderRadius: 15, alignItems: 'center', justifyContent: 'center', marginTop: 4, minHeight: 52 },
  text: { color: '#fff', fontSize: 15, fontWeight: '800' },
});

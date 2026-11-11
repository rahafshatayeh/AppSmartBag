import { ActivityIndicator, View } from 'react-native';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { colors } from '../theme';
import LoginScreen from '../screens/LoginScreen';
import RegisterScreen from '../screens/RegisterScreen';
import DashboardScreen from '../screens/DashboardScreen';
import LogScreen from '../screens/LogScreen';
import SettingsScreen from '../screens/SettingsScreen';
import ProfileScreen from '../screens/ProfileScreen';
import PackingListScreen from '../screens/PackingListScreen';
import FaceSetupScreen from '../screens/FaceSetupScreen';
import WeightScreen from '../screens/WeightScreen';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();
const icons = { Dashboard: 'home', Weight: 'barbell', Packing: 'bag-handle', Log: 'time', Profile: 'person-circle', Settings: 'settings' };

function MainTabs() {
  const { t, language } = useLanguage();
  return <Tab.Navigator screenOptions={({ route }) => ({
    headerStyle: { backgroundColor: colors.bg },
    headerTintColor: colors.text,
    headerTitleStyle: { fontWeight: '800' },
    tabBarStyle: { backgroundColor: colors.card, borderTopColor: colors.border, height: 62, paddingTop: 5, paddingBottom: 7 },
    tabBarLabelStyle: { fontSize: 10, fontWeight: '700' },
    tabBarActiveTintColor: colors.primary,
    tabBarInactiveTintColor: colors.muted,
    tabBarIcon: ({ color, size }) => <Ionicons name={icons[route.name]} size={size} color={color} />,
  })}>
    <Tab.Screen name="Dashboard" component={DashboardScreen} options={{ title: t('dashboard') }} />
    <Tab.Screen name="Weight" component={WeightScreen} options={{ title: language === 'ar' ? 'الوزن' : 'Weight' }} />
    <Tab.Screen name="Packing" component={PackingListScreen} options={{ title: t('packing') }} />
    <Tab.Screen name="Log" component={LogScreen} options={{ title: t('log') }} />
    <Tab.Screen name="Profile" component={ProfileScreen} options={{ title: t('profile') }} />
    <Tab.Screen name="Settings" component={SettingsScreen} options={{ title: t('settings') }} />
  </Tab.Navigator>;
}

function AuthStack() {
  return <Stack.Navigator screenOptions={{ headerShown: false }}>
    <Stack.Screen name="Login" component={LoginScreen} />
    <Stack.Screen name="Register" component={RegisterScreen} />
  </Stack.Navigator>;
}

function MainStack() {
  return <Stack.Navigator screenOptions={{ headerShown: false }}>
    <Stack.Screen name="MainTabs" component={MainTabs} />
    <Stack.Screen name="FaceSetup" component={FaceSetupScreen} />
  </Stack.Navigator>;
}

export default function AppNavigator() {
  const { user, loading } = useAuth();
  if (loading) return <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center' }}><ActivityIndicator size="large" color={colors.primary} /></View>;
  return <NavigationContainer theme={{ ...DefaultTheme, colors: { ...DefaultTheme.colors, background: colors.bg, card: colors.card, text: colors.text, border: colors.border, primary: colors.primary } }}>{user ? <MainStack /> : <AuthStack />}</NavigationContainer>;
}

import { createContext, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';

const AuthContext = createContext(null);
const USERS_KEY = 'bag_users';
const SESSION_KEY = 'bag_session';
const hash = (text) => Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, text);

const loadUsers = async () => {
  try { return JSON.parse((await AsyncStorage.getItem(USERS_KEY)) || '[]'); }
  catch { return []; }
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try { const session = await AsyncStorage.getItem(SESSION_KEY); if (session) setUser(JSON.parse(session)); }
      catch {}
      setLoading(false);
    })();
  }, []);

  const startSession = async (entry) => {
    const session = { name: entry.name, email: entry.email, gender: entry.gender || null };
    await AsyncStorage.setItem(SESSION_KEY, JSON.stringify(session));
    setUser(session);
  };
  const register = async (name, email, password, gender) => {
    const users = await loadUsers();
    const normalizedEmail = email.trim().toLowerCase();
    if (users.some((entry) => entry.email === normalizedEmail)) throw new Error('emailTaken');
    const newUser = { name: name.trim(), email: normalizedEmail, passwordHash: await hash(password), gender };
    await AsyncStorage.setItem(USERS_KEY, JSON.stringify([...users, newUser]));
    await startSession(newUser);
  };
  const login = async (email, password, gender) => {
    const users = await loadUsers();
    const normalizedEmail = email.trim().toLowerCase();
    const found = users.find((entry) => entry.email === normalizedEmail);
    if (!found || found.passwordHash !== await hash(password)) throw new Error('loginFailed');
    const updated = { ...found, gender };
    await AsyncStorage.setItem(USERS_KEY, JSON.stringify(users.map((entry) => entry.email === normalizedEmail ? updated : entry)));
    await startSession(updated);
  };
  const updateProfile = async (name, email) => {
    if (!user) return;
    const normalizedEmail = email.trim().toLowerCase();
    const users = await loadUsers();
    if (users.some((entry) => entry.email === normalizedEmail && entry.email !== user.email)) throw new Error('emailTaken');
    const updatedUsers = users.map((entry) => entry.email === user.email ? { ...entry, name: name.trim(), email: normalizedEmail } : entry);
    const session = { name: name.trim(), email: normalizedEmail, gender: user.gender || null };
    if (normalizedEmail !== user.email) {
      const oldListKey = `smart_bag_packing_list:${user.email}`;
      const newListKey = `smart_bag_packing_list:${normalizedEmail}`;
      const savedList = await AsyncStorage.getItem(oldListKey);
      if (savedList && !(await AsyncStorage.getItem(newListKey))) await AsyncStorage.setItem(newListKey, savedList);
      if (savedList) await AsyncStorage.removeItem(oldListKey);
    }
    await AsyncStorage.setItem(USERS_KEY, JSON.stringify(updatedUsers));
    await AsyncStorage.setItem(SESSION_KEY, JSON.stringify(session));
    setUser(session);
  };
  const logout = async () => { await AsyncStorage.removeItem(SESSION_KEY); setUser(null); };

  return <AuthContext.Provider value={{ user, loading, register, login, logout, updateProfile }}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);

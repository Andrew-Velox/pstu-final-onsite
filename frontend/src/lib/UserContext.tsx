"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import { listUsers, type User } from "@/lib/api";

interface UserContextValue {
  users: User[];
  activeUser: User | null;
  setActiveUser: (user: User) => void;
  loading: boolean;
  refreshUsers: () => Promise<void>;
}

const UserContext = createContext<UserContextValue>({
  users: [],
  activeUser: null,
  setActiveUser: () => {},
  loading: true,
  refreshUsers: async () => {},
});

export function UserProvider({ children }: { children: ReactNode }) {
  const [users, setUsers] = useState<User[]>([]);
  const [activeUser, setActiveUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Keep the latest activeUser in a ref so refreshUsers can auto-select the
  // first user without depending on `activeUser` itself. Otherwise the
  // effect below would re-fire after the auto-select, causing a double fetch.
  const activeUserRef = useRef<User | null>(activeUser);
  activeUserRef.current = activeUser;

  const refreshUsers = useCallback(async () => {
    try {
      const data = await listUsers();
      setUsers(data);
      // Auto-select the first user only when nothing is selected yet.
      if (data.length > 0 && !activeUserRef.current) {
        setActiveUser(data[0]);
        activeUserRef.current = data[0];
      }
    } catch (err) {
      console.error("Failed to fetch users — is the backend running?", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUsers();
  }, [refreshUsers]);

  return (
    <UserContext.Provider
      value={{ users, activeUser, setActiveUser, loading, refreshUsers }}
    >
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  return useContext(UserContext);
}

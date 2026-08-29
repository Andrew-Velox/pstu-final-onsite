"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
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

  const refreshUsers = useCallback(async () => {
    try {
      const data = await listUsers();
      setUsers(data);
      if (data.length > 0 && !activeUser) {
        setActiveUser(data[0]);
      }
    } catch {
      console.error("Failed to fetch users — is the backend running?");
    } finally {
      setLoading(false);
    }
  }, [activeUser]);

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

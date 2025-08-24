import { create } from "zustand";

type Profile = { email: string; name?: string; roles: string[] };

type State = {
  accessToken: string | null;
  profile: Profile | null;
  setAccessToken: (t: string, p: Profile) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
  hasRole: (r: string) => boolean;
};

export const useAuthStore = create<State>((set, get) => ({
  accessToken: null,
  profile: null,
  setAccessToken: (t, p) => set({ accessToken: t, profile: p }),
  logout: () => set({ accessToken: null, profile: null }),
  isAuthenticated: () => !!get().accessToken,
  hasRole: (r) => !!get().profile?.roles?.includes(r),
}));
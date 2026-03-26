export interface AuthUser {
  id: number;
  username: string;
  email: string;
  roles: string[];
  avatar?: string | null;
}

export interface RegisterPayload {
  username: string;
  email: string;
  password1: string;
  password2: string;
  roles: string[];
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface AuthResponse {
  success: boolean;
  token: string;
  user: AuthUser;
}

export type FieldErrors = Record<string, string[]>;
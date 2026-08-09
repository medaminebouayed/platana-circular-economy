import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap, throwError, catchError } from 'rxjs';
import { Router } from '@angular/router';

export interface User {
  email: string;
  role: 'USER' | 'ADMIN';
  name: string;
  avatar: string;
  roleLabel: string;
}

interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number; // seconds
  email: string;
  role: 'USER' | 'ADMIN';
  name: string;
  avatar: string;
  roleLabel: string;
}

const STORAGE_USER = 'platana-user';
const STORAGE_TOKEN = 'platana-token';
const STORAGE_EXPIRY = 'platana-token-expiry'; // ISO date string

@Injectable({ providedIn: 'root' })
export class AuthService {

  private readonly API = '/api/auth';
  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUserSubject.asObservable();

  // Timer reference for auto-logout
  private expiryTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private http: HttpClient, private router: Router) {
    this.restoreSession();
  }

  // ─────────────────────────────────────────────────────────────
  // Session Restore
  // ─────────────────────────────────────────────────────────────
  private restoreSession(): void {
    try {
      const stored = localStorage.getItem(STORAGE_USER);
      const expiry = localStorage.getItem(STORAGE_EXPIRY);
      if (stored && expiry) {
        if (new Date(expiry) > new Date()) {
          // Token still valid
          this.currentUserSubject.next(JSON.parse(stored));
          this.scheduleAutoLogout(new Date(expiry));
        } else {
          // Token already expired at app start → clean up
          this.clearStorage();
        }
      }
    } catch {
      this.clearStorage();
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Token management
  // ─────────────────────────────────────────────────────────────
  getToken(): string | null {
    return localStorage.getItem(STORAGE_TOKEN);
  }

  isTokenExpired(): boolean {
    const expiry = localStorage.getItem(STORAGE_EXPIRY);
    if (!expiry) return true;
    return new Date(expiry) <= new Date();
  }

  private scheduleAutoLogout(expiryDate: Date): void {
    if (this.expiryTimer) clearTimeout(this.expiryTimer);
    const msUntilExpiry = expiryDate.getTime() - Date.now();
    if (msUntilExpiry <= 0) {
      this.autoLogout();
      return;
    }
    this.expiryTimer = setTimeout(() => this.autoLogout(), msUntilExpiry);
  }

  private autoLogout(): void {
    const role = this.currentUserValue?.role;
    this.clearStorage();
    this.currentUserSubject.next(null);
    if (role === 'ADMIN') {
      this.router.navigate(['/login/admin'], { queryParams: { expired: '1' } });
    } else {
      this.router.navigate(['/login/user'], { queryParams: { expired: '1' } });
    }
  }

  private clearStorage(): void {
    localStorage.removeItem(STORAGE_USER);
    localStorage.removeItem(STORAGE_TOKEN);
    localStorage.removeItem(STORAGE_EXPIRY);
  }

  private storeSession(res: AuthResponse): User {
    const user: User = {
      email: res.email,
      role: res.role,
      name: res.name,
      avatar: res.avatar,
      roleLabel: res.roleLabel,
    };
    const expiryDate = new Date(Date.now() + res.expires_in * 1000);
    localStorage.setItem(STORAGE_USER, JSON.stringify(user));
    localStorage.setItem(STORAGE_TOKEN, res.access_token);
    localStorage.setItem(STORAGE_EXPIRY, expiryDate.toISOString());
    this.currentUserSubject.next(user);
    this.scheduleAutoLogout(expiryDate);
    return user;
  }

  // ─────────────────────────────────────────────────────────────
  // Auth operations
  // ─────────────────────────────────────────────────────────────
  public get currentUserValue(): User | null {
    return this.currentUserSubject.value;
  }

  login(email: string, password: string, role: 'USER' | 'ADMIN'): Observable<User> {
    return this.http.post<AuthResponse>(`${this.API}/login`, { email, password, role }).pipe(
      tap(res => {
        const user = this.storeSession(res);
        if (user.role === 'ADMIN') {
          this.router.navigate(['/dashboard']);
        } else {
          this.router.navigate(['/user-portal']);
        }
      }),
      // Map AuthResponse → User for subscribers
      tap(() => {}),
      catchError(err => throwError(() => err))
    ) as any;
  }

  register(name: string, email: string, password: string): Observable<User> {
    return this.http.post<AuthResponse>(`${this.API}/register`, { name, email, password }).pipe(
      tap(res => {
        this.storeSession(res);
        this.router.navigate(['/user-portal']);
      }),
      catchError(err => throwError(() => err))
    ) as any;
  }

  logout(): void {
    if (this.expiryTimer) clearTimeout(this.expiryTimer);
    const role = this.currentUserValue?.role;
    this.clearStorage();
    this.currentUserSubject.next(null);
    if (role === 'ADMIN') {
      this.router.navigate(['/login/admin']);
    } else {
      this.router.navigate(['/login/user']);
    }
  }

  /** Silent logout without navigation (used by interceptor before it navigates) */
  logoutSilent(): void {
    if (this.expiryTimer) clearTimeout(this.expiryTimer);
    this.clearStorage();
    this.currentUserSubject.next(null);
  }

  isAuthenticated(): boolean {
    return !!this.currentUserValue && !this.isTokenExpired();
  }

  hasRole(roles: ('USER' | 'ADMIN')[]): boolean {
    const user = this.currentUserValue;
    if (!user) return false;
    return roles.includes(user.role);
  }

  isLoginRoute(url: string): boolean {
    return url.includes('/login/') || url.includes('/register');
  }

  // ─────────────────────────────────────────────────────────────
  // Profile / Password management
  // ─────────────────────────────────────────────────────────────

  /** Update display name. On success, refreshes the local session with the new JWT. */
  updateProfile(name: string): Observable<User> {
    return this.http.put<any>(`${this.API}/profile`, { name }).pipe(
      tap(res => {
        // The backend returns a fresh TokenResponse — store it
        this.storeSession(res);
      }),
      catchError(err => throwError(() => err))
    ) as any;
  }

  /** Change password. Returns an observable that completes on success. */
  changePassword(currentPassword: string, newPassword: string): Observable<{ status: string; message: string }> {
    return this.http.put<{ status: string; message: string }>(
      `${this.API}/password`,
      { current_password: currentPassword, new_password: newPassword }
    ).pipe(
      catchError(err => throwError(() => err))
    );
  }
}

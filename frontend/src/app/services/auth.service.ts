import { Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable } from 'rxjs';

export interface User {
  email: string;
  name: string;
  role: 'admin' | 'rse' | 'atelier' | 'revente';
  roleLabel: string;
  avatar: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$: Observable<User | null> = this.currentUserSubject.asObservable();

  constructor(private router: Router) {
    // Check if session exists in local storage
    const storedUser = localStorage.getItem('platana_user');
    if (storedUser) {
      try {
        this.currentUserSubject.next(JSON.parse(storedUser));
      } catch (e) {
        localStorage.removeItem('platana_user');
      }
    }
  }

  public get currentUserValue(): User | null {
    return this.currentUserSubject.value;
  }

  login(email: string, role: 'admin' | 'rse' | 'atelier' | 'revente'): boolean {
    let name = 'Collaborateur Platana';
    let roleLabel = 'Collaborateur';

    if (role === 'admin') {
      name = 'Thomas Dubois';
      roleLabel = 'Administrateur Principal';
    } else if (role === 'rse') {
      name = 'Sophie Martin';
      roleLabel = 'Responsable RSE & Conformité';
    } else if (role === 'atelier') {
      name = 'Marc Lefevre';
      roleLabel = 'Directeur Atelier Reconditionnement';
    } else if (role === 'revente') {
      name = 'Julie Moreau';
      roleLabel = 'Responsable Pricing & Revente';
    }

    const user: User = {
      email,
      name,
      role,
      roleLabel,
      avatar: `https://api.dicebear.com/7.x/adventurer/svg?seed=${name}`
    };

    localStorage.setItem('platana_user', JSON.stringify(user));
    this.currentUserSubject.next(user);
    return true;
  }

  logout() {
    localStorage.removeItem('platana_user');
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }

  isAuthenticated(): boolean {
    return this.currentUserSubject.value !== null;
  }

  hasRole(roles: string[]): boolean {
    const user = this.currentUserValue;
    if (!user) return false;
    if (user.role === 'admin') return true; // admin has access to everything
    return roles.includes(user.role);
  }
}

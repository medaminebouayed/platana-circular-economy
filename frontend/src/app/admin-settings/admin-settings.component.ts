import { Component, OnInit } from '@angular/core';
import { AuthService } from '../services/auth.service';
import { ApiService } from '../services/api.service';

@Component({
  selector: 'app-admin-settings',
  templateUrl: './admin-settings.component.html',
  styleUrls: ['./admin-settings.component.css']
})
export class AdminSettingsComponent implements OnInit {
  user$ = this.authService.currentUser$;

  // ── UI Preferences ──────────────────────────────────────────
  isDarkTheme = false;
  emailNotifs = true;
  autoRefreshQueue = true;
  gradeDriftAlert = true;
  driftThreshold = 15;

  prefsSaving = false;
  prefsSuccess = false;
  prefsError = '';

  // ── Profile ─────────────────────────────────────────────────
  profileName = '';
  profileSaving = false;
  profileSuccess = false;
  profileError = '';

  // ── Password ────────────────────────────────────────────────
  currentPassword = '';
  newPassword = '';
  confirmPassword = '';
  passwordSaving = false;
  passwordSuccess = false;
  passwordError = '';

  constructor(public authService: AuthService, private api: ApiService) {}

  ngOnInit() {
    this.isDarkTheme = document.body.classList.contains('dark-theme');
    this.emailNotifs = localStorage.getItem('platana-email-notifs') !== 'false';
    this.autoRefreshQueue = localStorage.getItem('platana-auto-refresh') !== 'false';
    this.gradeDriftAlert = localStorage.getItem('platana-drift-alert') !== 'false';
    this.driftThreshold = Number(localStorage.getItem('platana-drift-threshold') || '15');

    const user = this.authService.currentUserValue;
    if (user) { this.profileName = user.name; }

    // Load preferences from MongoDB
    this.api.getMe().subscribe({
      next: (me) => {
        if (me.preferences) {
          const p = me.preferences;
          if (p.isDarkTheme !== undefined) this.isDarkTheme = p.isDarkTheme;
          if (p.emailNotifs !== undefined) this.emailNotifs = p.emailNotifs;
          if (p.autoRefreshQueue !== undefined) this.autoRefreshQueue = p.autoRefreshQueue;
          if (p.gradeDriftAlert !== undefined) this.gradeDriftAlert = p.gradeDriftAlert;
          if (p.driftThreshold !== undefined) this.driftThreshold = p.driftThreshold;
          document.body.classList.toggle('dark-theme', this.isDarkTheme);
        }
      }
    });
  }

  toggleTheme() {
    this.isDarkTheme = !this.isDarkTheme;
    localStorage.setItem('platana-theme', this.isDarkTheme ? 'dark' : 'light');
    document.body.classList.toggle('dark-theme', this.isDarkTheme);
  }

  savePreferences() {
    localStorage.setItem('platana-email-notifs', String(this.emailNotifs));
    localStorage.setItem('platana-auto-refresh', String(this.autoRefreshQueue));
    localStorage.setItem('platana-drift-alert', String(this.gradeDriftAlert));
    localStorage.setItem('platana-drift-threshold', String(this.driftThreshold));
    localStorage.setItem('platana-theme', this.isDarkTheme ? 'dark' : 'light');
    document.body.classList.toggle('dark-theme', this.isDarkTheme);

    const payload = {
      isDarkTheme: this.isDarkTheme,
      emailNotifs: this.emailNotifs,
      autoRefreshQueue: this.autoRefreshQueue,
      gradeDriftAlert: this.gradeDriftAlert,
      driftThreshold: this.driftThreshold
    };

    this.prefsSaving = true;
    this.prefsError = '';
    this.api.updatePreferences(payload).subscribe({
      next: () => {
        this.prefsSaving = false;
        this.prefsSuccess = true;
        setTimeout(() => (this.prefsSuccess = false), 2500);
      },
      error: (err) => {
        this.prefsSaving = false;
        this.prefsError = err?.error?.detail || 'Erreur lors de la sauvegarde des paramètres.';
      }
    });
  }

  saveProfile() {
    if (!this.profileName.trim()) {
      this.profileError = 'Le nom ne peut pas être vide.';
      return;
    }
    this.profileSaving = true;
    this.profileError = '';
    this.profileSuccess = false;
    this.authService.updateProfile(this.profileName.trim()).subscribe({
      next: () => {
        this.profileSaving = false;
        this.profileSuccess = true;
        setTimeout(() => (this.profileSuccess = false), 2500);
      },
      error: (err: any) => {
        this.profileSaving = false;
        this.profileError = err?.error?.detail || 'Erreur lors de la mise à jour du profil.';
      }
    });
  }

  changePassword() {
    this.passwordError = '';
    if (!this.currentPassword) {
      this.passwordError = 'Veuillez saisir votre mot de passe actuel.';
      return;
    }
    if (this.newPassword.length < 6) {
      this.passwordError = 'Le nouveau mot de passe doit contenir au moins 6 caractères.';
      return;
    }
    if (this.newPassword !== this.confirmPassword) {
      this.passwordError = 'Les mots de passe ne correspondent pas.';
      return;
    }
    this.passwordSaving = true;
    this.passwordSuccess = false;
    this.authService.changePassword(this.currentPassword, this.newPassword).subscribe({
      next: () => {
        this.passwordSaving = false;
        this.passwordSuccess = true;
        this.currentPassword = '';
        this.newPassword = '';
        this.confirmPassword = '';
        setTimeout(() => (this.passwordSuccess = false), 2500);
      },
      error: (err: any) => {
        this.passwordSaving = false;
        this.passwordError = err?.error?.detail || 'Erreur lors du changement de mot de passe.';
      }
    });
  }
}

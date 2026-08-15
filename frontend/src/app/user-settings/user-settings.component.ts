import { Component, OnInit } from '@angular/core';
import { AuthService } from '../services/auth.service';
import { ApiService } from '../services/api.service';
import { TranslationService } from '../services/translation.service';

@Component({
  selector: 'app-user-settings',
  templateUrl: './user-settings.component.html',
  styleUrls: ['./user-settings.component.css']
})
export class UserSettingsComponent implements OnInit {
  user$ = this.authService.currentUser$;

  // ── UI Preferences ──────────────────────────────────────────
  isDarkTheme = false;
  notificationsEnabled = true;
  emailNotifs = true;
  language = 'fr';

  prefsSaving = false;
  prefsSuccess = false;
  prefsError = '';

  // ── Profile ─────────────────────────────────────────────────
  profileName = '';
  profileEmail = '';
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

  constructor(public authService: AuthService, private api: ApiService, public translation: TranslationService) {}

  onLanguageChange() {
    this.translation.setLang(this.language);
  }

  ngOnInit() {
    this.isDarkTheme = document.body.classList.contains('dark-theme');
    this.notificationsEnabled = localStorage.getItem('platana-notifs') !== 'false';
    this.emailNotifs = localStorage.getItem('platana-email-notifs') !== 'false';
    this.language = localStorage.getItem('platana-lang') || 'fr';

    const user = this.authService.currentUserValue;
    if (user) {
      this.profileName = user.name;
      this.profileEmail = user.email;
    }

    // Load stored preferences from MongoDB
    this.api.getMe().subscribe({
      next: (me) => {
        if (me.preferences) {
          const p = me.preferences;
          if (p.isDarkTheme !== undefined) this.isDarkTheme = p.isDarkTheme;
          if (p.notificationsEnabled !== undefined) this.notificationsEnabled = p.notificationsEnabled;
          if (p.emailNotifs !== undefined) this.emailNotifs = p.emailNotifs;
          if (p.language) this.language = p.language;
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
    localStorage.setItem('platana-notifs', String(this.notificationsEnabled));
    localStorage.setItem('platana-email-notifs', String(this.emailNotifs));
    localStorage.setItem('platana-lang', this.language);
    localStorage.setItem('platana-theme', this.isDarkTheme ? 'dark' : 'light');
    document.body.classList.toggle('dark-theme', this.isDarkTheme);

    const payload = {
      isDarkTheme: this.isDarkTheme,
      notificationsEnabled: this.notificationsEnabled,
      emailNotifs: this.emailNotifs,
      language: this.language
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
        this.prefsError = err?.error?.detail || this.translation.t('settings.prefsSaveError');
      }
    });
  }

  saveProfile() {
    if (!this.profileName.trim()) {
      this.profileError = this.translation.t('settings.nameRequired');
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
        this.profileError = err?.error?.detail || this.translation.t('settings.profileUpdateError');
      }
    });
  }

  changePassword() {
    this.passwordError = '';
    if (!this.currentPassword) {
      this.passwordError = this.translation.t('settings.currentPasswordRequired');
      return;
    }
    if (this.newPassword.length < 6) {
      this.passwordError = this.translation.t('settings.newPasswordMin');
      return;
    }
    if (this.newPassword !== this.confirmPassword) {
      this.passwordError = this.translation.t('settings.passwordMismatch');
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
        this.passwordError = err?.error?.detail || this.translation.t('settings.passwordChangeError');
      }
    });
  }
}

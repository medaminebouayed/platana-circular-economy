import { Component, OnInit } from '@angular/core';
import { AuthService } from '../services/auth.service';
import { ApiService } from '../services/api.service';
import { TranslationService } from '../services/translation.service';

interface TrainingJob {
  job_id: string;
  model: string;
  status: string;
  exit_code?: number;
  requested_at: string;
  started_at?: string;
  finished_at?: string;
  log_tail?: string;
}

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
  maxAIFaults = 10;

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

  // ── Continuous Learning / Drift Alert ──────────────────────
  driftStats: any = null;
  driftLoading = false;
  driftError = '';
  trainingJobs: TrainingJob[] = [];
  jobsLoading = false;
  jobsError = '';
  trainingBusy: 'pricing' | 'cv' | null = null;
  trainingMessage = '';
  trainingError = false;
  private readonly AUTO_REFRESH_MS = 30000;
  private refreshTimer: ReturnType<typeof setInterval> | null = null;

  constructor(public authService: AuthService, private api: ApiService, public translation: TranslationService) {}

  ngOnInit() {
    this.isDarkTheme = document.body.classList.contains('dark-theme');
    this.emailNotifs = localStorage.getItem('platana-email-notifs') !== 'false';
    this.autoRefreshQueue = localStorage.getItem('platana-auto-refresh') !== 'false';
    this.gradeDriftAlert = localStorage.getItem('platana-drift-alert') !== 'false';
    this.driftThreshold = Number(localStorage.getItem('platana-drift-threshold') || '15');
    this.maxAIFaults = Number(localStorage.getItem('platana-max-ai-faults') || '10');

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
          if (p.maxAIFaults !== undefined) this.maxAIFaults = p.maxAIFaults;
          document.body.classList.toggle('dark-theme', this.isDarkTheme);
        }
        this.syncRefreshTimer();
      }
    });

    this.loadDriftStats();
    this.loadTrainingJobs();
    this.syncRefreshTimer();
  }

  ngOnDestroy() {
    if (this.refreshTimer) clearInterval(this.refreshTimer);
  }

  private syncRefreshTimer(): void {
    if (this.autoRefreshQueue && !this.refreshTimer) {
      this.refreshTimer = setInterval(() => this.loadTrainingJobs(), this.AUTO_REFRESH_MS);
    } else if (!this.autoRefreshQueue && this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  toggleAutoRefresh() {
    this.autoRefreshQueue = !this.autoRefreshQueue;
    localStorage.setItem('platana-auto-refresh', String(this.autoRefreshQueue));
    this.syncRefreshTimer();
  }

  // ── Drift alert banner ─────────────────────────────────────
  loadDriftStats() {
    this.driftLoading = true;
    this.driftError = '';
    this.api.getDriftStats().subscribe({
      next: (stats) => { this.driftStats = stats; this.driftLoading = false; },
      error: (err) => {
        this.driftLoading = false;
        this.driftError = err?.error?.detail || this.translation.t('adminSettings.driftLoadError');
      }
    });
  }

  // ── Continuous learning ────────────────────────────────────
  loadTrainingJobs() {
    this.jobsLoading = true;
    this.api.getTrainingJobs(10).subscribe({
      next: (res) => { this.trainingJobs = res.items || []; this.jobsLoading = false; },
      error: (err) => {
        this.jobsLoading = false;
        this.jobsError = err?.error?.detail || this.translation.t('adminSettings.jobsLoadError');
      }
    });
  }

  triggerTraining(model: 'pricing' | 'cv') {
    if (this.trainingBusy) return;
    this.trainingBusy = model;
    this.trainingMessage = '';
    this.trainingError = false;
    this.api.createTrainingJob(model).subscribe({
      next: () => {
        this.trainingMessage = this.translation.tWith('adminSettings.retrainStarted', { model });
        this.trainingBusy = null;
        this.loadTrainingJobs();
      },
      error: (err) => {
        this.trainingBusy = null;
        this.trainingError = true;
        this.trainingMessage = err?.error?.detail || this.translation.tWith('adminSettings.retrainFailed', { model });
      }
    });
  }

  isJobActive(model: 'pricing' | 'cv'): boolean {
    return this.trainingJobs.some(j => j.model === model && (j.status === 'QUEUED' || j.status === 'RUNNING'));
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
    localStorage.setItem('platana-max-ai-faults', String(this.maxAIFaults));
    localStorage.setItem('platana-theme', this.isDarkTheme ? 'dark' : 'light');
    document.body.classList.toggle('dark-theme', this.isDarkTheme);

    const payload = {
      isDarkTheme: this.isDarkTheme,
      emailNotifs: this.emailNotifs,
      autoRefreshQueue: this.autoRefreshQueue,
      gradeDriftAlert: this.gradeDriftAlert,
      driftThreshold: this.driftThreshold,
      maxAIFaults: this.maxAIFaults
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
        this.prefsError = err?.error?.detail || this.translation.t('adminSettings.prefsSaveError');
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

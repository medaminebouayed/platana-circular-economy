import { Component } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { TranslationService } from '../services/translation.service';

@Component({
  selector: 'app-user-login',
  templateUrl: './user-login.component.html',
  styleUrls: ['./user-login.component.css']
})
export class UserLoginComponent {
  email = '';
  password = '';
  isLoading = false;
  error = '';
  sessionExpired = false;

  constructor(
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute,
    public translation: TranslationService
  ) {
    // Show session expiry message if redirected with ?expired=1
    this.sessionExpired = this.route.snapshot.queryParamMap.get('expired') === '1';

    // Redirect already-logged-in users
    if (!this.sessionExpired) {
      if (this.authService.isAuthenticated() && this.authService.hasRole(['USER'])) {
        this.router.navigate(['/user-portal']);
      } else if (this.authService.isAuthenticated() && this.authService.hasRole(['ADMIN'])) {
        this.router.navigate(['/dashboard']);
      }
    }
  }

  submit() {
    if (!this.email || !this.password) { this.error = this.translation.t('login.fillAllFields'); return; }
    this.isLoading = true;
    this.error = '';
    this.sessionExpired = false;
    this.authService.login(this.email, this.password, 'USER').subscribe({
      error: (err) => {
        this.isLoading = false;
        this.error = err?.error?.detail || this.translation.t('login.invalidCredentials');
      }
    });
  }
}

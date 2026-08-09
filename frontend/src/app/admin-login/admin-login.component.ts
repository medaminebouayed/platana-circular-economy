import { Component } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-admin-login',
  templateUrl: './admin-login.component.html',
  styleUrls: ['./admin-login.component.css']
})
export class AdminLoginComponent {
  email = '';
  password = '';
  isLoading = false;
  error = '';
  sessionExpired = false;

  constructor(
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute
  ) {
    this.sessionExpired = this.route.snapshot.queryParamMap.get('expired') === '1';

    if (!this.sessionExpired) {
      if (this.authService.isAuthenticated() && this.authService.hasRole(['ADMIN'])) {
        this.router.navigate(['/dashboard']);
      } else if (this.authService.isAuthenticated() && this.authService.hasRole(['USER'])) {
        this.router.navigate(['/user-portal']);
      }
    }
  }

  submit() {
    if (!this.email || !this.password) { this.error = 'Veuillez remplir tous les champs.'; return; }
    this.isLoading = true;
    this.error = '';
    this.sessionExpired = false;
    this.authService.login(this.email, this.password, 'ADMIN').subscribe({
      error: (err) => {
        this.isLoading = false;
        this.error = err?.error?.detail || 'Identifiants administrateur invalides.';
      }
    });
  }
}

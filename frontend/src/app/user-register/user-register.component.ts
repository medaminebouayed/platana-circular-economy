import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-user-register',
  templateUrl: './user-register.component.html',
  styleUrls: ['./user-register.component.css']
})
export class UserRegisterComponent {
  name = '';
  email = '';
  password = '';
  isLoading = false;
  error = '';

  constructor(private authService: AuthService, private router: Router) {
    if (this.authService.isAuthenticated()) {
      if (this.authService.hasRole(['ADMIN'])) {
        this.router.navigate(['/dashboard']);
      } else {
        this.router.navigate(['/user-portal']);
      }
    }
  }

  submit() {
    if (!this.name || !this.email || !this.password) {
      this.error = 'Veuillez remplir tous les champs.';
      return;
    }
    
    this.isLoading = true;
    this.error = '';

    this.authService.register(this.name, this.email, this.password).subscribe({
      next: () => {
        this.router.navigate(['/user-portal']);
      },
      error: (err) => {
        this.isLoading = false;
        this.error = err?.error?.detail || 'Erreur lors de l\'inscription.';
      }
    });
  }
}

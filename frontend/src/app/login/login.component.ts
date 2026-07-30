import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css']
})
export class LoginComponent implements OnInit {
  email = 'thomas.dubois@platana.fr';
  role: 'admin' | 'rse' | 'atelier' | 'revente' = 'admin';
  errorMessage = '';

  constructor(private authService: AuthService, private router: Router) {}

  ngOnInit() {
    // If already logged in, go straight to appropriate screen
    if (this.authService.isAuthenticated()) {
      this.redirectUser();
    }
  }

  onSubmit() {
    if (!this.email) {
      this.errorMessage = 'Veuillez saisir votre adresse email professionnelle.';
      return;
    }

    const success = this.authService.login(this.email, this.role);
    if (success) {
      this.redirectUser();
    } else {
      this.errorMessage = 'Échec de la connexion. Vérifiez vos identifiants.';
    }
  }

  selectRoleProfile(profile: 'admin' | 'rse' | 'atelier' | 'revente') {
    this.role = profile;
    if (profile === 'admin') this.email = 'thomas.dubois@platana.fr';
    if (profile === 'rse') this.email = 'sophie.martin@platana.fr';
    if (profile === 'atelier') this.email = 'marc.lefevre@platana.fr';
    if (profile === 'revente') this.email = 'julie.moreau@platana.fr';
  }

  private redirectUser() {
    const user = this.authService.currentUserValue;
    if (!user) return;
    
    if (user.role === 'atelier') {
      this.router.navigate(['/grading']);
    } else {
      this.router.navigate(['/dashboard']);
    }
  }
}

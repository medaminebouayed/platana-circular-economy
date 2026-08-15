import { Component, OnInit } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { AuthService, User } from './services/auth.service';
import { TranslationService } from './services/translation.service';
import { filter } from 'rxjs/operators';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit {
  currentUser: User | null = null;
  currentRoute = '';
  mobileMenuOpen = false;
  isDarkTheme = false;

  constructor(
    public authService: AuthService,
    public translation: TranslationService,
    private router: Router
  ) {
    this.initTheme();
  }

  initTheme() {
    const savedTheme = localStorage.getItem('platana-theme');
    if (savedTheme) {
      this.isDarkTheme = savedTheme === 'dark';
    } else {
      // Check system preference
      this.isDarkTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    this.applyTheme();
  }

  toggleTheme() {
    this.isDarkTheme = !this.isDarkTheme;
    localStorage.setItem('platana-theme', this.isDarkTheme ? 'dark' : 'light');
    this.applyTheme();
  }

  setLang(lang: string) {
    this.translation.setLang(lang);
  }

  applyTheme() {
    if (this.isDarkTheme) {
      document.body.classList.add('dark-theme');
    } else {
      document.body.classList.remove('dark-theme');
    }
  }

  ngOnInit() {
    this.authService.currentUser$.subscribe(user => {
      this.currentUser = user;
    });

    // Track active route changes for active class highlighting
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: any) => {
      this.currentRoute = event.urlAfterRedirects || event.url;
      this.mobileMenuOpen = false; // close sidebar on route change
    });
  }

  toggleMobileMenu() {
    this.mobileMenuOpen = !this.mobileMenuOpen;
  }



  getRouteTitle(): string {
    if (this.currentRoute.includes('dashboard')) return this.translation.t('route.dashboard');
    if (this.currentRoute.includes('user-portal')) return this.translation.t('route.userPortal');
    if (this.currentRoute.includes('grading')) return this.translation.t('route.grading');
    if (this.currentRoute.includes('pricing')) return this.translation.t('route.pricing');
    if (this.currentRoute.includes('product-sheet')) return this.translation.t('route.productSheet');
    if (this.currentRoute.includes('logistics')) return this.translation.t('route.logistics');
    if (this.currentRoute.includes('settings/admin')) return this.translation.t('route.adminSettings');
    if (this.currentRoute.includes('settings/user')) return this.translation.t('route.settings');
    return this.translation.t('route.platana');
  }
}

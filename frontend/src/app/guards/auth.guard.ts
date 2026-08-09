import { Injectable } from '@angular/core';
import { CanActivate, ActivatedRouteSnapshot, Router, UrlTree } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Injectable({ providedIn: 'root' })
export class AuthGuard implements CanActivate {
  constructor(private auth: AuthService, private router: Router) {}

  canActivate(route: ActivatedRouteSnapshot): boolean | UrlTree {
    const user = this.auth.currentUserValue;

    // Not authenticated at all — redirect to user login
    if (!user || this.auth.isTokenExpired()) {
      this.auth.logoutSilent();
      return this.router.createUrlTree(['/login/user']);
    }

    // Check allowed roles (data.roles set on the route)
    const requiredRoles: string[] = route.data['roles'] || [];
    if (requiredRoles.length > 0 && !requiredRoles.includes(user.role)) {
      // User tries to access admin pages — redirect to correct portal
      if (user.role === 'USER') {
        return this.router.createUrlTree(['/user-portal']);
      }
      return this.router.createUrlTree(['/dashboard']);
    }

    return true;
  }
}

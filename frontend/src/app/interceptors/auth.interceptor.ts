import { Injectable } from '@angular/core';
import {
  HttpInterceptor, HttpRequest, HttpHandler, HttpEvent, HttpErrorResponse
} from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { AuthService } from '../services/auth.service';
import { Router } from '@angular/router';

@Injectable()
export class AuthInterceptor implements HttpInterceptor {

  constructor(private auth: AuthService, private router: Router) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    const token = this.auth.getToken();

    // Attach JWT bearer token to all API requests
    const authReq = token
      ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
      : req;

    return next.handle(authReq).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.status === 401) {
          // Token expired or invalid — auto logout and redirect
          const role = this.auth.currentUserValue?.role;
          this.auth.logoutSilent();
          if (role === 'ADMIN') {
            this.router.navigate(['/login/admin'], { queryParams: { expired: '1' } });
          } else {
            this.router.navigate(['/login/user'], { queryParams: { expired: '1' } });
          }
        }
        return throwError(() => error);
      })
    );
  }
}

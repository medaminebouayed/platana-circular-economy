import { Component, Input, OnChanges, OnDestroy, SimpleChanges } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-product-image',
  template: `
    <img *ngIf="objectUrl" [src]="objectUrl" [alt]="alt" [class]="cssClass" (error)="onError()">
    <div *ngIf="!objectUrl && !failed" class="img-loading" [class]="cssClass">📸</div>
    <div *ngIf="failed" class="no-img" [class]="cssClass">📸</div>
  `,
  styles: [`
    :host { display: block; }
    img, .img-loading, .no-img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      border-radius: inherit;
    }
    .img-loading, .no-img {
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--bg-color, #f1f5f9);
      font-size: 1.5rem;
      opacity: 0.6;
    }
  `]
})
export class ProductImageComponent implements OnChanges, OnDestroy {
  @Input() productId = '';
  @Input() index = 0;
  @Input() alt = 'Photo';
  @Input() cssClass = '';

  objectUrl: string | null = null;
  failed = false;
  private sub: Subscription | null = null;

  constructor(private http: HttpClient) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['productId'] || changes['index']) {
      this.loadImage();
    }
  }

  ngOnDestroy(): void {
    this.revokeUrl();
    this.sub?.unsubscribe();
  }

  onError(): void {
    this.failed = true;
    this.revokeUrl();
  }

  private loadImage(): void {
    this.revokeUrl();
    this.failed = false;
    this.sub?.unsubscribe();

    if (!this.productId) return;

    this.sub = this.http
      .get(`/api/products/${this.productId}/images/${this.index}`, { responseType: 'blob' })
      .subscribe({
        next: (blob) => {
          this.objectUrl = URL.createObjectURL(blob);
        },
        error: () => {
          this.failed = true;
        }
      });
  }

  private revokeUrl(): void {
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }
  }
}

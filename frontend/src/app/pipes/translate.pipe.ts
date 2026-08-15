import { Pipe, PipeTransform } from '@angular/core';
import { TranslationService } from '../services/translation.service';

@Pipe({
  name: 'translate',
  pure: false
})
export class TranslatePipe implements PipeTransform {
  constructor(private translation: TranslationService) {}

  transform(key: string, params?: Record<string, string | number>): string {
    if (key === null || key === undefined) return '';
    if (params && Object.keys(params).length > 0) {
      return this.translation.tWith(key, params);
    }
    return this.translation.t(key);
  }
}
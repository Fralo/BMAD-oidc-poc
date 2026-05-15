import { provideHttpClient, withFetch } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AuthService } from './auth-service';
import { Me } from './auth.types';

describe('AuthService', () => {
  let service: AuthService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch()),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(AuthService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  it('initial me() is null', () => {
    expect(service.me()).toBeNull();
  });

  it('loadMe() on 200 sets me() to the parsed body', async () => {
    const me: Me = { sub: 's1', preferred_username: 'alice' };
    const pending = service.loadMe();
    httpTesting.expectOne('/api/me').flush(me);
    await pending;
    expect(service.me()).toEqual(me);
  });

  it('loadMe() on 401 sets me() to null and resolves (does not reject)', async () => {
    const pending = service.loadMe();
    httpTesting.expectOne('/api/me').flush(null, { status: 401, statusText: 'Unauthorized' });
    await expect(pending).resolves.toBeUndefined();
    expect(service.me()).toBeNull();
  });

  it('clear() resets me() to null after a successful load', async () => {
    const me: Me = { sub: 's1', preferred_username: 'alice' };
    const pending = service.loadMe();
    httpTesting.expectOne('/api/me').flush(me);
    await pending;
    expect(service.me()).toEqual(me);
    service.clear();
    expect(service.me()).toBeNull();
  });

  it('setMe() writes through the signal', () => {
    const me: Me = { sub: 's2', preferred_username: 'bob' };
    service.setMe(me);
    expect(service.me()).toEqual(me);
    service.setMe(null);
    expect(service.me()).toBeNull();
  });
});

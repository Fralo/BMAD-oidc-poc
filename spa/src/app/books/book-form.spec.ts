import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import {
  BOOK_FORM_ADD_BUTTON_IDLE,
  BOOK_FORM_ADD_BUTTON_SUBMITTING,
  BOOK_FORM_EDIT_BUTTON_IDLE,
  BOOK_FORM_EDIT_BUTTON_SUBMITTING,
  BOOK_FORM_EDIT_CANCEL_LABEL,
  BOOK_FORM_SERVER_CSRF_INVALID,
  BOOK_FORM_SERVER_GENERIC,
  BOOK_FORM_SERVER_INVALID_INPUT,
  BOOK_FORM_SERVER_NETWORK,
  BOOK_FORM_SERVER_SESSION_EXPIRED,
  BOOK_FORM_VALIDATION_MULTIPLE,
  BOOK_FORM_VALIDATION_PAGES_POSITIVE,
  BOOK_FORM_VALIDATION_PAGES_REQUIRED,
  BOOK_FORM_VALIDATION_TITLE_REQUIRED,
  BookForm,
} from './book-form';
import { Book } from './book.types';
import { BooksService } from './books-service';

function mkBook(overrides: Partial<Book> = {}): Book {
  return {
    id: 1,
    title: 'Dune',
    pages: 688,
    status: 'to-read',
    created_at: '2026-05-16T00:00:00Z',
    updated_at: '2026-05-16T00:00:00Z',
    ...overrides,
  };
}

async function renderForm(): Promise<{
  fixture: ComponentFixture<BookForm>;
  httpTesting: HttpTestingController;
  booksService: BooksService;
}> {
  await TestBed.configureTestingModule({
    imports: [BookForm],
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withFetch()),
      provideHttpClientTesting(),
    ],
  }).compileComponents();

  const fixture = TestBed.createComponent(BookForm);
  fixture.componentRef.setInput('variant', 'add');
  fixture.detectChanges();
  await fixture.whenStable();

  const httpTesting = TestBed.inject(HttpTestingController);
  const booksService = TestBed.inject(BooksService);
  return { fixture, httpTesting, booksService };
}

function getEl(fixture: ComponentFixture<BookForm>): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function getInput(fixture: ComponentFixture<BookForm>, controlName: string): HTMLInputElement {
  return getEl(fixture).querySelector(
    `[formcontrolname="${controlName}"]`,
  ) as HTMLInputElement;
}

function getSelect(fixture: ComponentFixture<BookForm>, controlName: string): HTMLSelectElement {
  return getEl(fixture).querySelector(
    `[formcontrolname="${controlName}"]`,
  ) as HTMLSelectElement;
}

function getSubmitButton(fixture: ComponentFixture<BookForm>): HTMLButtonElement {
  return getEl(fixture).querySelector('button.book-form-submit') as HTMLButtonElement;
}

function fillInput(input: HTMLInputElement | HTMLSelectElement, value: string): void {
  input.value = value;
  input.dispatchEvent(new Event('input'));
  input.dispatchEvent(new Event('change'));
}

function fillForm(
  fixture: ComponentFixture<BookForm>,
  values: { title?: string; pages?: string; status?: string } = {},
): void {
  if (values.title !== undefined) {
    fillInput(getInput(fixture, 'title'), values.title);
  }
  if (values.pages !== undefined) {
    fillInput(getInput(fixture, 'pages'), values.pages);
  }
  if (values.status !== undefined) {
    fillInput(getSelect(fixture, 'status'), values.status);
  }
}

describe('BookForm [variant=add]', () => {
  let httpTesting: HttpTestingController;

  afterEach(() => {
    httpTesting?.verify();
  });

  describe('default state', () => {
    it('renders three labelled inputs, a status select with three options, and the "Add book" button', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;
      const el = getEl(r.fixture);

      // Three labels
      const labels = el.querySelectorAll('label.book-form-label');
      expect(labels.length).toBe(3);
      const labelTexts = Array.from(labels).map(
        (l) => l.querySelector('.book-form-label-text')?.textContent?.trim(),
      );
      expect(labelTexts).toEqual(['Title', 'Page count', 'Status']);

      // Inputs
      const titleInput = getInput(r.fixture, 'title');
      expect(titleInput).not.toBeNull();
      expect(titleInput.type).toBe('text');

      const pagesInput = getInput(r.fixture, 'pages');
      expect(pagesInput).not.toBeNull();
      expect(pagesInput.type).toBe('number');
      expect(pagesInput.getAttribute('min')).toBe('1');

      // Status select with three options
      const statusSelect = getSelect(r.fixture, 'status');
      expect(statusSelect).not.toBeNull();
      const options = Array.from(statusSelect.querySelectorAll('option')).map((o) => o.value);
      expect(options).toEqual(['to-read', 'reading', 'finished']);
      expect(statusSelect.value).toBe('to-read');

      // Submit button
      const button = getSubmitButton(r.fixture);
      expect(button.textContent?.trim()).toBe(BOOK_FORM_ADD_BUTTON_IDLE);
      expect(button.disabled).toBe(false);

      // No Cancel button in variant="add"
      const buttons = el.querySelectorAll('button');
      expect(buttons.length).toBe(1);

      // No initial error message
      expect(el.querySelector('app-error-message')).toBeNull();
    });
  });

  describe('submitting state (happy path)', () => {
    it('disables and relabels the button while the create is in-flight, then resets the form on success', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;

      fillForm(r.fixture, { title: 'Dune', pages: '688', status: 'to-read' });
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      // Invoke onSubmit directly so we can await its Promise.
      const pending = r.fixture.componentInstance.onSubmit();
      r.fixture.detectChanges();

      // Button should be disabled and relabelled BEFORE flushing
      const button = getSubmitButton(r.fixture);
      expect(button.disabled).toBe(true);
      expect(button.textContent?.trim()).toBe(BOOK_FORM_ADD_BUTTON_SUBMITTING);

      // The request was fired
      const req = httpTesting.expectOne({ method: 'POST', url: '/v1/books' });
      expect(req.request.body).toEqual({ title: 'Dune', pages: 688, status: 'to-read' });

      // Flush success
      req.flush(mkBook({ id: 42, title: 'Dune', pages: 688, status: 'to-read' }));
      await pending;
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      // Button restored
      const buttonAfter = getSubmitButton(r.fixture);
      expect(buttonAfter.disabled).toBe(false);
      expect(buttonAfter.textContent?.trim()).toBe(BOOK_FORM_ADD_BUTTON_IDLE);

      // Form reset
      expect(getInput(r.fixture, 'title').value).toBe('');
      expect(getInput(r.fixture, 'pages').value).toBe('');
      expect(getSelect(r.fixture, 'status').value).toBe('to-read');

      // No error rendered
      expect(getEl(r.fixture).querySelector('app-error-message')).toBeNull();

      // Books signal was updated by BooksService.create (prepend)
      expect(r.booksService.books().length).toBe(1);
      expect(r.booksService.books()[0].title).toBe('Dune');
    });

    it('trims whitespace from the title before sending the create payload', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;

      fillForm(r.fixture, { title: '  Dune  ', pages: '688' });
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const pending = r.fixture.componentInstance.onSubmit();
      r.fixture.detectChanges();

      const req = httpTesting.expectOne('/v1/books');
      expect(req.request.body.title).toBe('Dune');
      req.flush(mkBook({ title: 'Dune' }));
      await pending;
    });
  });

  describe('validation-error state', () => {
    it('empty title: renders inline error mentioning "Title", dispatches NO request, and preserves the empty value', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;

      // Fill pages so only title is invalid
      fillForm(r.fixture, { title: '', pages: '100' });
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const form = getEl(r.fixture).querySelector('form') as HTMLFormElement;
      form.dispatchEvent(new Event('submit'));
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const errEl = getEl(r.fixture).querySelector('app-error-message p');
      expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_VALIDATION_TITLE_REQUIRED);
      expect(errEl?.textContent).toContain('Title');

      httpTesting.expectNone('/v1/books');
      expect(getInput(r.fixture, 'title').value).toBe('');
      expect(getInput(r.fixture, 'pages').value).toBe('100');
    });

    it('whitespace-only title: rejects, preserves the "   " value, no HTTP request', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;

      fillForm(r.fixture, { title: '   ', pages: '100' });
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const form = getEl(r.fixture).querySelector('form') as HTMLFormElement;
      form.dispatchEvent(new Event('submit'));
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const errEl = getEl(r.fixture).querySelector('app-error-message p');
      expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_VALIDATION_TITLE_REQUIRED);

      httpTesting.expectNone('/v1/books');
      expect(getInput(r.fixture, 'title').value).toBe('   ');
    });

    it('missing pages (null): renders inline error mentioning "Page count", no HTTP request', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;

      fillForm(r.fixture, { title: 'Dune' });
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const form = getEl(r.fixture).querySelector('form') as HTMLFormElement;
      form.dispatchEvent(new Event('submit'));
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const errEl = getEl(r.fixture).querySelector('app-error-message p');
      expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_VALIDATION_PAGES_REQUIRED);
      expect(errEl?.textContent).toContain('Page count');

      httpTesting.expectNone('/v1/books');
      expect(getInput(r.fixture, 'title').value).toBe('Dune');
    });

    it('pages=0: renders inline error mentioning "positive", no HTTP request, value preserved', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;

      fillForm(r.fixture, { title: 'Dune', pages: '0' });
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const form = getEl(r.fixture).querySelector('form') as HTMLFormElement;
      form.dispatchEvent(new Event('submit'));
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const errEl = getEl(r.fixture).querySelector('app-error-message p');
      expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_VALIDATION_PAGES_POSITIVE);

      httpTesting.expectNone('/v1/books');
      expect(getInput(r.fixture, 'pages').value).toBe('0');
    });

    it('pages=-1: rejects with the "positive" copy, no HTTP request', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;

      fillForm(r.fixture, { title: 'Dune', pages: '-1' });
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const form = getEl(r.fixture).querySelector('form') as HTMLFormElement;
      form.dispatchEvent(new Event('submit'));
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const errEl = getEl(r.fixture).querySelector('app-error-message p');
      expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_VALIDATION_PAGES_POSITIVE);

      httpTesting.expectNone('/v1/books');
      expect(getInput(r.fixture, 'pages').value).toBe('-1');
    });
  });

  describe('server-error state', () => {
    it('422 invalid_input: renders mapped inline copy and preserves the entered values', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;

      fillForm(r.fixture, { title: 'Dune', pages: '688', status: 'reading' });
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const pending = r.fixture.componentInstance.onSubmit();
      r.fixture.detectChanges();

      const req = httpTesting.expectOne('/v1/books');
      req.flush(
        {
          errorCode: 'invalid_input',
          message: 'Request validation failed',
          detail: [{ loc: ['body', 'title'], msg: 'too short', type: 'value_error' }],
        },
        { status: 422, statusText: 'Unprocessable Entity' },
      );
      await pending;
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      // Error rendered with mapped copy
      const errEl = getEl(r.fixture).querySelector('app-error-message p');
      expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_SERVER_INVALID_INPUT);

      // Inputs preserve their values
      expect(getInput(r.fixture, 'title').value).toBe('Dune');
      expect(getInput(r.fixture, 'pages').value).toBe('688');
      expect(getSelect(r.fixture, 'status').value).toBe('reading');

      // Button restored
      const button = getSubmitButton(r.fixture);
      expect(button.disabled).toBe(false);
      expect(button.textContent?.trim()).toBe(BOOK_FORM_ADD_BUTTON_IDLE);
    });

    it('403 csrf_invalid: renders the CSRF-mapped inline copy', async () => {
      const r = await renderForm();
      httpTesting = r.httpTesting;

      fillForm(r.fixture, { title: 'Dune', pages: '688' });
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const pending = r.fixture.componentInstance.onSubmit();
      r.fixture.detectChanges();

      const req = httpTesting.expectOne('/v1/books');
      req.flush(
        { errorCode: 'csrf_invalid', message: 'CSRF token invalid' },
        { status: 403, statusText: 'Forbidden' },
      );
      await pending;
      r.fixture.detectChanges();
      await r.fixture.whenStable();

      const errEl = getEl(r.fixture).querySelector('app-error-message p');
      expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_SERVER_CSRF_INVALID);

      // Values preserved
      expect(getInput(r.fixture, 'title').value).toBe('Dune');
      expect(getInput(r.fixture, 'pages').value).toBe('688');
    });
  });
});

async function renderEditForm(book: Book): Promise<{
  fixture: ComponentFixture<BookForm>;
  httpTesting: HttpTestingController;
  booksService: BooksService;
}> {
  await TestBed.configureTestingModule({
    imports: [BookForm],
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withFetch()),
      provideHttpClientTesting(),
    ],
  }).compileComponents();

  const fixture = TestBed.createComponent(BookForm);
  fixture.componentRef.setInput('variant', 'edit');
  fixture.componentRef.setInput('book', book);
  fixture.detectChanges();
  await fixture.whenStable();

  const httpTesting = TestBed.inject(HttpTestingController);
  const booksService = TestBed.inject(BooksService);
  return { fixture, httpTesting, booksService };
}

function getCancelButton(fixture: ComponentFixture<BookForm>): HTMLButtonElement | null {
  return getEl(fixture).querySelector('button.book-form-cancel') as HTMLButtonElement | null;
}

describe('BookForm [variant=edit]', () => {
  let httpTesting: HttpTestingController;

  afterEach(() => {
    httpTesting?.verify();
  });

  it('renders pre-filled inputs, a Save primary button, and a Cancel secondary button', async () => {
    const book = mkBook({ id: 42, title: 'Dune', pages: 688, status: 'reading' });
    const r = await renderEditForm(book);
    httpTesting = r.httpTesting;

    expect(getInput(r.fixture, 'title').value).toBe('Dune');
    expect(getInput(r.fixture, 'pages').value).toBe('688');
    expect(getSelect(r.fixture, 'status').value).toBe('reading');

    const submit = getSubmitButton(r.fixture);
    expect(submit.textContent?.trim()).toBe(BOOK_FORM_EDIT_BUTTON_IDLE);
    expect(submit.disabled).toBe(false);

    const cancel = getCancelButton(r.fixture);
    expect(cancel).not.toBeNull();
    expect(cancel?.textContent?.trim()).toBe(BOOK_FORM_EDIT_CANCEL_LABEL);
    expect(cancel?.getAttribute('type')).toBe('button');
    expect(cancel?.disabled).toBe(false);
  });

  it('submitting state: disables both buttons and relabels Save to "Saving…"; emits save on success', async () => {
    const book = mkBook({ id: 42, title: 'Dune', pages: 688, status: 'to-read' });
    const r = await renderEditForm(book);
    httpTesting = r.httpTesting;

    const saveSpy = vi.fn();
    const cancelSpy = vi.fn();
    r.fixture.componentInstance.bookSaved.subscribe(saveSpy);
    r.fixture.componentInstance.editCancelled.subscribe(cancelSpy);

    // Modify a field
    fillInput(getInput(r.fixture, 'title'), 'Dune (revised)');
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const pending = r.fixture.componentInstance.onSubmit();
    r.fixture.detectChanges();

    const submit = getSubmitButton(r.fixture);
    const cancel = getCancelButton(r.fixture);
    expect(submit.disabled).toBe(true);
    expect(submit.textContent?.trim()).toBe(BOOK_FORM_EDIT_BUTTON_SUBMITTING);
    expect(cancel?.disabled).toBe(true);

    const req = httpTesting.expectOne({ method: 'PATCH', url: '/v1/books/42' });
    expect(req.request.body).toEqual({
      title: 'Dune (revised)',
      pages: 688,
      status: 'to-read',
    });
    req.flush(mkBook({ id: 42, title: 'Dune (revised)', pages: 688, status: 'to-read' }));
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    expect(saveSpy).toHaveBeenCalledTimes(1);
    expect(cancelSpy).not.toHaveBeenCalled();
  });

  it('Cancel emits cancel output and dispatches NO HTTP request', async () => {
    const book = mkBook({ id: 42, title: 'Dune', pages: 688, status: 'to-read' });
    const r = await renderEditForm(book);
    httpTesting = r.httpTesting;

    const saveSpy = vi.fn();
    const cancelSpy = vi.fn();
    r.fixture.componentInstance.bookSaved.subscribe(saveSpy);
    r.fixture.componentInstance.editCancelled.subscribe(cancelSpy);

    // Modify a field then cancel
    fillInput(getInput(r.fixture, 'title'), 'Changed');
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const cancelBtn = getCancelButton(r.fixture);
    cancelBtn?.click();
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    httpTesting.expectNone('/v1/books/42');
    expect(cancelSpy).toHaveBeenCalledTimes(1);
    expect(saveSpy).not.toHaveBeenCalled();
  });

  it('validation error: renders inline copy, dispatches NO HTTP request, preserves entered values, emits nothing', async () => {
    const book = mkBook({ id: 42, title: 'Dune', pages: 688, status: 'to-read' });
    const r = await renderEditForm(book);
    httpTesting = r.httpTesting;

    const saveSpy = vi.fn();
    const cancelSpy = vi.fn();
    r.fixture.componentInstance.bookSaved.subscribe(saveSpy);
    r.fixture.componentInstance.editCancelled.subscribe(cancelSpy);

    // Clear the title -> invalid
    fillInput(getInput(r.fixture, 'title'), '');
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const form = getEl(r.fixture).querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit'));
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const errEl = getEl(r.fixture).querySelector('app-error-message p');
    expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_VALIDATION_TITLE_REQUIRED);

    httpTesting.expectNone('/v1/books/42');
    expect(saveSpy).not.toHaveBeenCalled();
    expect(cancelSpy).not.toHaveBeenCalled();
    expect(getInput(r.fixture, 'title').value).toBe('');
  });

  it('validation error with multiple invalid fields: renders the multi-field copy', async () => {
    const book = mkBook({ id: 42, title: 'Dune', pages: 688, status: 'to-read' });
    const r = await renderEditForm(book);
    httpTesting = r.httpTesting;

    fillInput(getInput(r.fixture, 'title'), '');
    fillInput(getInput(r.fixture, 'pages'), '0');
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const form = getEl(r.fixture).querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit'));
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const errEl = getEl(r.fixture).querySelector('app-error-message p');
    expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_VALIDATION_MULTIPLE);
    httpTesting.expectNone('/v1/books/42');
  });

  it('server-error: 401 session_expired and network errors map through the exhaustive switch', async () => {
    const book = mkBook({ id: 42, title: 'Dune', pages: 688, status: 'to-read' });
    const r = await renderEditForm(book);
    httpTesting = r.httpTesting;

    const pending = r.fixture.componentInstance.onSubmit();
    r.fixture.detectChanges();
    const req = httpTesting.expectOne('/v1/books/42');
    req.flush(
      { errorCode: 'session_expired', message: 'no session' },
      { status: 401, statusText: 'Unauthorized' },
    );
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const errEl = getEl(r.fixture).querySelector('app-error-message p');
    expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_SERVER_SESSION_EXPIRED);
  });

  it('server-error: network error renders the network-mapped inline copy', async () => {
    const book = mkBook({ id: 42, title: 'Dune', pages: 688, status: 'to-read' });
    const r = await renderEditForm(book);
    httpTesting = r.httpTesting;

    const pending = r.fixture.componentInstance.onSubmit();
    r.fixture.detectChanges();
    const req = httpTesting.expectOne('/v1/books/42');
    req.error(new ProgressEvent('error'), { status: 0, statusText: '' });
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const errEl = getEl(r.fixture).querySelector('app-error-message p');
    expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_SERVER_NETWORK);
  });

  it('server-error: book_not_found maps to the generic copy (the row may have been deleted in another tab)', async () => {
    const book = mkBook({ id: 42, title: 'Dune', pages: 688, status: 'to-read' });
    const r = await renderEditForm(book);
    httpTesting = r.httpTesting;

    const pending = r.fixture.componentInstance.onSubmit();
    r.fixture.detectChanges();
    const req = httpTesting.expectOne('/v1/books/42');
    req.flush(
      { errorCode: 'book_not_found', message: 'gone' },
      { status: 404, statusText: 'Not Found' },
    );
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const errEl = getEl(r.fixture).querySelector('app-error-message p');
    expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_SERVER_GENERIC);
  });

  it('server-error: 422 invalid_input renders inline copy, preserves values, restores button, emits nothing', async () => {
    const book = mkBook({ id: 42, title: 'Dune', pages: 688, status: 'to-read' });
    const r = await renderEditForm(book);
    httpTesting = r.httpTesting;

    const saveSpy = vi.fn();
    const cancelSpy = vi.fn();
    r.fixture.componentInstance.bookSaved.subscribe(saveSpy);
    r.fixture.componentInstance.editCancelled.subscribe(cancelSpy);

    fillInput(getInput(r.fixture, 'title'), 'Dune (typo)');
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const pending = r.fixture.componentInstance.onSubmit();
    r.fixture.detectChanges();

    const req = httpTesting.expectOne('/v1/books/42');
    req.flush(
      { errorCode: 'invalid_input', message: 'bad' },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const errEl = getEl(r.fixture).querySelector('app-error-message p');
    expect(errEl?.textContent?.trim()).toBe(BOOK_FORM_SERVER_INVALID_INPUT);

    // Inputs preserved
    expect(getInput(r.fixture, 'title').value).toBe('Dune (typo)');
    expect(getInput(r.fixture, 'pages').value).toBe('688');
    expect(getSelect(r.fixture, 'status').value).toBe('to-read');

    // Button restored
    const submit = getSubmitButton(r.fixture);
    expect(submit.disabled).toBe(false);
    expect(submit.textContent?.trim()).toBe(BOOK_FORM_EDIT_BUTTON_IDLE);

    expect(saveSpy).not.toHaveBeenCalled();
    expect(cancelSpy).not.toHaveBeenCalled();
  });
});

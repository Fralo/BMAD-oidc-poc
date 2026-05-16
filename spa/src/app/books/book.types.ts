export type BookStatus = 'to-read' | 'reading' | 'finished';

export interface Book {
  id: number;
  title: string;
  pages: number;
  status: BookStatus;
  created_at: string;
  updated_at: string;
}

export interface BookCreate {
  title: string;
  pages: number;
  status: BookStatus;
}

export type BookUpdate = Partial<{
  title: string;
  pages: number;
  status: BookStatus;
}>;

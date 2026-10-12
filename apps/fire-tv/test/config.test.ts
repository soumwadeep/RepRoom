import {DEFAULT_API_BASE, normaliseBase} from '../src/config';

describe('normaliseBase', () => {
  it('accepts a bare host and gives it a scheme', () => {
    expect(normaliseBase('192.168.1.20')).toBe('http://192.168.1.20');
  });

  it('accepts host:port and a full URL', () => {
    expect(normaliseBase('192.168.1.20:8420')).toBe('http://192.168.1.20:8420');
    expect(normaliseBase('http://localhost:8420')).toBe('http://localhost:8420');
  });

  it('keeps https, because the camera page may be TLS-served', () => {
    expect(normaliseBase('https://192.168.1.20:8420')).toBe('https://192.168.1.20:8420');
  });

  it('trims whitespace and trailing slashes', () => {
    expect(normaliseBase('  http://localhost:8420///  ')).toBe('http://localhost:8420');
  });

  it('rejects an empty value, a path, a bad port and a non-http scheme', () => {
    expect(normaliseBase('')).toBeNull();
    expect(normaliseBase('http://localhost:8420/session')).toBeNull();
    expect(normaliseBase('http://localhost:99999')).toBeNull();
    expect(normaliseBase('ftp://host')).toBeNull();
  });

  it('accepts the shipped default unchanged', () => {
    expect(normaliseBase(DEFAULT_API_BASE)).toBe(DEFAULT_API_BASE);
  });
});

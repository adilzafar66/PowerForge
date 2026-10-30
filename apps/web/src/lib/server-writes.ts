// The HTTP layer reports confirmed writes; the mounted provider owns cache policy.
// There is no module-level QueryClient or server cache shared between requests.
const listeners = new Set<(path: string) => void>();
export function onServerWrite(listener: (path: string) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
export function serverWriteConfirmed(path: string) {
  listeners.forEach((listener) => listener(path));
}

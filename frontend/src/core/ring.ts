/* Fixed-capacity ring buffer for client-side session-window charts
   (spec §9.3 / §11: ~300 pts since the page opened — NOT persistent history). */
export class RingBuffer<T> {
  private buf: T[] = []

  constructor(readonly capacity = 300) {}

  push(item: T): void {
    this.buf.push(item)
    if (this.buf.length > this.capacity) this.buf.shift()
  }

  items(): T[] {
    return this.buf
  }

  get length(): number {
    return this.buf.length
  }

  clear(): void {
    this.buf = []
  }
}

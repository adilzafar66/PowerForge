// Test-process preload: fix displayed dates without freezing scheduler clocks.
const RealDate = Date;
global.Date = class extends RealDate {
  constructor(...args) {
    super(...(args.length ? args : ["2026-01-20T12:00:00Z"]));
  }
};

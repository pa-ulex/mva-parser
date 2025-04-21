const airac = require('airac-cc');

const today = new Date();
const cycle = airac.Cycle.fromDate(today);

const identifier = cycle.identifier;
const start = cycle.effectiveStart.toISOString().slice(0, 10);
const adjustedEnd = new Date(cycle.effectiveEnd);
adjustedEnd.setDate(adjustedEnd.getDate() + 1);
const end = adjustedEnd.toISOString().slice(0, 10);

console.log(`IDENTIFIER=${identifier}`);
console.log(`START=${start}`);
console.log(`END=${end}`);

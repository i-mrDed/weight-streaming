```javascript
// List the model ids you can select in your IDE
const res = await fetch("http://127.0.0.1:8765/v1/models");
const models = await res.json();
console.log(models.map((m) => m.id));
```

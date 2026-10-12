import '@testing-library/jest-dom/vitest';

import { afterEach } from 'vitest';
import { resetModelSelection } from '../hooks/modelSelection';

// The picked model is shared app state; start every test from "auto".
afterEach(() => {
  resetModelSelection();
});

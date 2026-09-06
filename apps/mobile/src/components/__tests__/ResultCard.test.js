import { render, screen } from '@testing-library/react-native';

import ResultCard from '../ResultCard';

describe('ResultCard', () => {
  it('renders nothing when there is no data', () => {
    const { toJSON } = render(<ResultCard data={null} />);
    expect(toJSON()).toBeNull();
  });

  it('renders the ALLOW badge and reason', () => {
    render(<ResultCard data={{ action: 'ALLOW', reason: 'routine request' }} />);
    expect(screen.getByText('Allowed')).toBeTruthy();
    expect(screen.getByText('routine request')).toBeTruthy();
  });

  it('renders the BLOCK badge for a nested decision shape', () => {
    render(<ResultCard data={{ decision: { action: 'BLOCK', reason: 'prompt injection' } }} />);
    expect(screen.getByText('Blocked')).toBeTruthy();
    expect(screen.getByText('prompt injection')).toBeTruthy();
  });

  it('shows the generated response section only when a response is present', () => {
    const { rerender } = render(<ResultCard data={{ action: 'ALLOW', reason: 'ok' }} />);
    expect(screen.queryByText('Generated response')).toBeNull();

    rerender(<ResultCard data={{ action: 'ALLOW', reason: 'ok', response: 'hello there' }} />);
    expect(screen.getByText('Generated response')).toBeTruthy();
    expect(screen.getByText('hello there')).toBeTruthy();
  });

  it('falls back to an UNKNOWN badge for an unrecognized action', () => {
    render(<ResultCard data={{ action: 'SOMETHING_NEW', reason: 'n/a' }} />);
    expect(screen.getByText('Unknown')).toBeTruthy();
  });
});

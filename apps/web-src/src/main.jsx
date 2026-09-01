import React from 'react';
import ReactDOM from 'react-dom/client';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { ChatHistoryProvider } from './context/ChatHistoryContext';
import App from './App';
import './styles/tokens.css';
import './App.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <ChatHistoryProvider>
          <App />
        </ChatHistoryProvider>
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>
);

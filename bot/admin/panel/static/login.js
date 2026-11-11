const params = new URLSearchParams(window.location.search);
const status = document.querySelector('#login-status');
const request = document.querySelector('#request-login');

const messages = {
  login_expired: 'That login link expired. Request a fresh one from the bot.',
  forbidden: 'That Telegram account is not authorized for the admin panel.',
  signed_out: 'You have been signed out.',
};

if (params.get('error')) {
  status.textContent = messages[params.get('error')] || 'Sign-in failed. Request a fresh link.';
  status.classList.add('error');
}

request.addEventListener('click', () => {
  status.classList.remove('error');
  status.textContent = 'Open your private chat with the bot and send /admin_panel.';
});
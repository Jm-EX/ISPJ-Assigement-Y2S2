-- Fix Admin1! account to have NULL role (master admin)
UPDATE users SET role = NULL, permissions = NULL WHERE username = 'Admin1!';

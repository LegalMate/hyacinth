# hyacinth
Python HTTP Client library for the Clio Manage API

[![Basic Checks](https://github.com/LegalMate/hyacinth/actions/workflows/basic.yml/badge.svg)](https://github.com/LegalMate/hyacinth/actions/workflows/basic.yml)

## Features

- OAuth2 token support
- Pagination via Cursors
- Rate limiting (by token)
- Update upstream tokens after refresh

## Usage

Clone `hyacinth` repository to your local environment:

```shell
git clone git@github.com:LegalMate/hyacinth.git
```

Install `hyacinth` in your project:
```python
poetry install git:ssh//git@github.com/LegalMate/harmonia.git
```

Import `hyacinth`:

```python
import hyacinth
```

Create a Session:

```python
s = hyacinth.Session(client_id=<client_id>,
                     client_secret=<client_secret>,
                     token=<token>)
```

Use the Session:

```python
me = s.get_who_am_i()
print(me)

=> {'id': 350963386, 'etag': '"14eb46ba60ce9c2e6a68f6d0d2c36334"', 'name': 'Anson MacKeracher'}
```

## Development

If you'd like to contribute to `hyacinth`'s development, here's how to
get your environment set up:

```sh
poetry install
```

Feel free to submit a Pull Request with any changes. Things are
low-key, and low-process for the time being. Don't be a stranger!

### Tests

Run the test suite via:

```sh
poetry run poe test
```

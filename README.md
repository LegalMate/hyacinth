# hyacinth
Python HTTP Client library for the Clio Manage API

## Features

- [ ] OAuth2 token support
- [x] Pagination via Cursors
- [ ] Rate limiting (by token)

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

1. `pipenv --python 3.10`
2. `poetry install`

Feel free to submit a Pull Request with any changes. Things are
low-key, and low-process for the time being. Don't be a stranger!

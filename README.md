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
pipenv install path/to/hyacinth
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

d## Development
1. `pipenv --python 3.10`
2. `pipenv install`

---
title: Testing external API calls
layout: post
author: Harry
categories:
  - testing
tags:
  - tdd
  - fakes
  - mocks
  - adapters
---

## Notes

common question, how do i write tests for external api calls


Let's take an example to do with logistics, we have a model of a shipment which contains a number
of order lines.  We also care about its estimated time of arrival (`eta`) and a bit of jargon
called the "incoterm".

```python
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

@dataclass
class OrderLine:
    sku: str
    qty: int


@dataclass
class Shipment:
    reference: str
    lines: List[OrderLine]
    eta: Optional[date]
    incoterm: str

    def save(self):
        ...
```


We want to sink our shipments model with a third party, the cargo freight company, via their API.
We have a couple of use cases, new shipment creation, and checking for updated etas:


Creating a new shipment isn't too hard:
```python
def create_shipment(quantities: Dict[str, int], incoterm):
    reference = uuid.uuid4().hex[:10]
    order_lines = [OrderLine(sku=sku, qty=qty) for sku, qty in quantities.items()]
    shipment = Shipment(reference=reference, lines=order_lines, eta=None, incoterm=incoterm)
    shipment.save()
    sync_to_api(shipment)
```


How do we sync to the API?  a simple post request, with a bit of datatype conversion and wrangling.

```python
def sync_to_api(shipment):
    requests.post(f'{API_URL}/shipments/', json={
        'client_reference': shipment.reference,
        'arrival_date': shipment.eta.isoformat(),
        'products': [
            {'sku': ol.sku, 'quantity': ol.quantity}
            for ol in shipment.lines
        ]
    })
```

Not too bad!  In a case like this, the typical reaction is to reach for mocks,
and _as long as things stay simple_, it's pretty manageable


```python
def test_create_shipment_does_post_to_external_api():
    with mock.patch('use_cases.requests') as mock_requests:
        shipment = create_shipment({'sku1': 10}, incoterm='EXW')
        expected_data = {
            'client_reference': shipment.reference,
            'arrival_date': None,
            'products': [{'sku': 'sku1', 'quantity': 10}],
        }
        assert mock_requests.post.call_args == mock.call(
            API_URL + '/shipments/', json=expected_data
        )
```

And you can imagine adding a few more tests, perhaps one that checks that
we do the date-to-isoformat conversion correctly, maybe one that checks we can handle multiple
lines.  Three tests, one mock each, we're ok.

The trouble is that it never stays quite that simple does it?  For example,
the cargo company may already have a shipment on record, because reasons.
So we first need to check whether they have a shipment on file, using
a GET request, and then we either do a POST if it's new, or a PUT for
an existing one:

```python
def get_shipment_id(our_reference) -> Optional[str]:
    their_shipments = requests.get(f"{API_URL}/shipments/").json()['items']
    return next(
        (s['id'] for s in their_shipments if s['client_reference'] == our_reference),
        None
    )



def sync_to_api(shipment):
    external_shipment_id = get_shipment_id(shipment.reference)
    if external_shipment_id is None:
        requests.post(f'{API_URL}/shipments/', json={
            'client_reference': shipment.reference,
            'arrival_date': shipment.eta,
            'products': [
                {'sku': ol.sku, 'quantity': ol.quantity}
                for ol in shipment.lines
            ]
        })

    else:
        requests.put(f'{API_URL}/shipments/{external_shipment_id}', json={
            'client_reference': shipment.reference,
            'arrival_date': shipment.eta,
            'products': [
                {'sku': ol.sku, 'quantity': ol.quantity}
                for ol in shipment.lines
            ]
        })



```

* because things are never easy, the third party has different reference numbers to us,
  so we need the `get_shipment_id()` function that finds the right one for us

* and we need to use POST if it's a new shipment, or PUT if it's an existing one.
  don't ask why they would know about a shipment before we do, it happens.

Already you can imagine we're going to need to write quite a few tests to cover all these options.

```python
def test_does_PUT_if_shipment_already_exists():
    with mock.patch('use_cases.uuid') as mock_uuid, mock.patch('use_cases.requests') as mock_requests:
        mock_uuid.uuid4.return_value.hex = 'our-id'
        mock_requests.get.return_value.json.return_value = {
            'items': [{'id': 'their-id', 'client_reference': 'our-id'}]
        }

        shipment = create_shipment({'sku1': 10}, incoterm='EXW')
        assert mock_requests.post.called is False
        expected_data = {
            'client_reference': 'our-id',
            'arrival_date': None,
            'products': [{'sku': 'sku1', 'quantity': 10}],
        }
        assert mock_requests.put.call_args == mock.call(
            API_URL + '/shipments/their-id/', json=expected_data
        )
```


yeesh.  This is getting less pleasant.  


But it gets better!  We want to poll our third party api now and again to get updated etas
for ours shipments.  Depending on the eta, we have some business logic about notifying
people of delays...


```python
def get_updated_eta(shipment):
    external_shipment_id = get_shipment_id(shipment.reference)
    if external_shipment_id is None:
        logging.warning(
            'tried to get updated eta for shipment %s not yet sent to partners',
            shipment.reference
        )
        return

    [journey] = requests.get(f"{API_URL}/shipments/{external_shipment_id}/journeys").json()['items']
    latest_eta = journey['eta']
    if latest_eta == shipment.eta:
        return
    logging.info(
        'setting new shipment eta for %s: %s (was %s)',
        shipment.reference, latest_eta, shipment.eta
    )
    if shipment.eta is not None and latest_eta > shipment.eta:
        notify_delay(shipment_ref=shipment.reference, delay=latest_eta - shipment.eta)
    if shipment.eta is None and shipment.incoterm == 'FOB' and len(shipment.lines) > 10:
        notify_new_large_shipment(shipment_ref=shipment.reference, eta=latest_eta)

    shipment.eta = latest_eta
    shipment.save()
```

I haven't coded up what all the tests would look like, but you could imagine them:

* a test that if the shipment does not exist, we log a warning.  Needs to mock `requests.get` or `get_shipment_id()`
* a test that if the eta has not changed, we do nothing.  Needs two different mocks on `requests.get`
* a test for the error case where the shipments api has no journeys
* a test for the edge case where the shipment has multiple journeys
* two tests to check that if the eta is is later than the current one, we do a notification.
* two test for the large shipments notification
* and a general test that we update the local eta and save it.

And each one of these tests needs to set up three or four mocks.  We're getting into what Ed Jung
calls [Mock Hell](https://www.youtube.com/watch?v=CdKaZ7boiZ4).

On top of our tests being hard to read and write, they're also brittle.  If we change the way we
import, from `import requests` to `from requests import get` (not that you'd ever do that, but
you get the point), then all our mocks break.  Or perhaps we decide to stop using
`requests.get()` because we want to use `requests.Session()` for whatever reason.


pros:
* no change to client code
* low effort
* everyone understands it

cons:
* tightly coupled
* brittle.  requests.get -> requests.Session().get will break it.
* need to remember to `@mock.patch` every single test that might
 end up invoking that api


- could mention vcr.py here.  ingenious but i've found it confuses ppl.

* and you still need an integration test or two, and maybe an E2E test.
  so you need a sandbox, or some way of faking it out irl



# step 1: DI

    example

- this will fix your brittleness and "remember to mock.patch" problem
- comes at the cost of a new "unnecessary" argument to your app code
* some people like that tho.


link to brandon "hoist your io" video


# step 2a: build an adapter. or a wrapper. or whatever you want to call it

- maybe not worth it if you really do only have that one api call

but if there's more, this is great.

    example goes here




# step 2b: integration tests for the adapter

* mention contract testing
* you still need to solve the sandbox problem here


# step 2c: unit tests for the things that use the adapter

* test pyramid yay


# step 2d: consider building a fake for CI

* once you've got an integration working, if it's not the core
  of you're app, you don't your CI builds to be flakey because
  a third party is flakey



    example here

pros: faster CI, faster local dev
cons: need a way to occasionally run tests against the real thing.
      also: more code


# general pros + cons re: adapters

pros:
 * no brittle mocks everywhere
 * decoupling; our app code is now no longer dependeent on the specific api
   we're calling. if it changes, or we change it, our app doesnt need to know
 * and our app code looks nicer too
 * we've created a clear separation between things that get unit tested
   and things that get integration tested

cons:
 * more code
 * DI is still a hard sell in the python world



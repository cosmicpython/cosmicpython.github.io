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

    example tbc

common solution. use mocks and mock.patch.  fine, actually, if you
have just one call to one endpoint

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

link to ed "mocking pitfalls" video


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



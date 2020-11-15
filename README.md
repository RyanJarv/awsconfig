# AWS Config Rules

## NonDefaultMetadataServer

It's possible in AWS to override the default Metadata server, this can be abused to root instances on launch if are able to modify VPC Route's. This rule checks if the "169.254.169.254/32" route is assigned to any RouteTable. You can only override the Metadata route with a /32, so currently we don't check for any larger CIDR ranges.

You can find more info on this on my [blog](https://blog.ryanjarv.sh/2020/10/19/imds-persistence.html).

## Quick Start

```
pip install rdk
rdk init # Set's up AWS config in your account
rdk deploy NonDefaultMetadataServer
```

You should now see this rule in the Config console.


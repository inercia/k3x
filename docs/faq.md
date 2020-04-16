# Frequently asked questions

###  I just want fresh clusters all the time. Can I have a _pool_ of clusters?

1. Create a ["New cluster..."](user-manual-creating-a-new-cluster.md) with
   your preferred settings. The cluster will be created and it will become the active one.
   Lets's call this `cluster-1`.
2. Then create a new cluster with _"New cluster with last settings"_. This will be `cluster-2`.
   After a while you will see some notification saying that `cluster-2` has been created and
   it is the active one.
3. Here comes the trick: to _recycle_ clusters. Press _\<Ctrl\>\<Shift\>\<Super\>K_.
   This will perform the following actions:
   * a non-active cluster will be selected as the new active cluster. In this case,
     **`cluster-1` will become the active cluster**.
   * your current cluster, **`cluster-2` will be destroyed** in the background.
   * a new cluster, **`cluster-3`, will be created in the background**.

Note well that `cluster-1` is available immediately as an active, fresh cluster, so
you don't have to wait for using it and deploying your application there. Next time you
recycle clusters, `cluster-3` will become the new active cluster. and so on...

### Can I use a remote Docker server?

Yes, you can, but things are a bit more complicated. Assuming your remote Docker server is
running at `remote.server`:

* your Docker server must be accessible from the machine where `k3x` is running.
  This can be with a simple TCP socket (using a Docker server address like
  `tcp://remote.server:2375`) or with a SSH connection (like `ssh://user@remote.server`).
  You can verify the connectivity by running a simple `DOCKER_HOST=<docker-address-address> docker info`.

* using a _local registry_ that is not _local_ makes things more difficult. For example, when using
  a registry like `registry.localhost:5000`, the DNS name `registry.localhost` is locally resolvable
  in your machine, either because many modern distros resolve all the `.localhost` machines to `127.0.0.1`,
  or because you added a line in `/etc/hosts`).
  But when the local registry is not really "local", then you must make it _resolvable_. You must then
  either add a line in `/etc/hosts` or add an entry in your DNS server for pointing to `remote.server`,
  and the registry port must be open in `remote.server`. If the registry port is `5000`, you could
  verify connectivity with `curl http://remote.server:5000/v2/_catalog`.
    
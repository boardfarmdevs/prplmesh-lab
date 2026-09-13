void __hidden
ubus_process_msg(struct ubus_context *ctx, struct ubus_msghdr_buf *buf, int fd)
{
	switch(buf->hdr.type) {
	case UBUS_MSG_STATUS:
	case UBUS_MSG_DATA:
		ubus_process_req_msg(ctx, buf, fd);
		break;

	case UBUS_MSG_INVOKE:
	case UBUS_MSG_UNSUBSCRIBE:
	case UBUS_MSG_NOTIFY:
		if (ctx->stack_depth) {
			ubus_queue_msg(ctx, buf);
			break;
		}

		ubus_process_obj_msg(ctx, buf, fd);
		break;
	case UBUS_MSG_MONITOR:
		if (ctx->monitor_cb)
			ctx->monitor_cb(ctx, buf->hdr.seq, buf->data);
		break;
	}
}

static void ubus_process_pending_msg(struct uloop_timeout *timeout)
{
	struct ubus_context *ctx = container_of(timeout, struct ubus_context, pending_timer);
	struct ubus_pending_msg *pending, *tmp;

	list_for_each_entry_safe(pending, tmp, &ctx->pending, list) {
		if (ctx->stack_depth)
			break;

		list_del(&pending->list);
		ubus_process_msg(ctx, &pending->hdr, -1);
		free(pending);
	}
}

void __hidden ubus_handle_data(struct uloop_fd *u, unsigned int events)
{
	struct ubus_context *ctx = container_of(u, struct ubus_context, sock);
	int recv_fd = -1;

	while (get_next_msg(ctx, &recv_fd)) {
		ubus_process_msg(ctx, &ctx->msgbuf, recv_fd);
		if (uloop_cancelling() || ctx->cancel_poll)
			break;
	}

	if (u->eof)
		ctx->connection_lost(ctx);
}
